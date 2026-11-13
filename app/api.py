import csv
import io
from datetime import date
from decimal import Decimal, InvalidOperation

from flask import Blueprint, Response, jsonify, request
from sqlalchemy import and_, func, or_, text
from sqlalchemy.exc import IntegrityError

from . import db
from .models import Category, Product, StockMovement

bp = Blueprint("api", __name__, url_prefix="/api")

MAX_QTY = 1_000_000_000
MAX_PRICE = Decimal("9999999999.99")
SORTABLE = {"sku", "name", "quantity", "price", "created_at", "updated_at"}


class ApiError(Exception):
    def __init__(self, message, status=400, details=None):
        self.message, self.status, self.details = message, status, details


@bp.errorhandler(ApiError)
def _api_error(e):
    body = {"error": e.message}
    if e.details:
        body["details"] = e.details
    return jsonify(body), e.status


@bp.after_request
def _no_store(resp):
    resp.headers["Cache-Control"] = "no-store"
    return resp


# ---------------------------------------------------------------- helpers
def _json():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError("Request body must be a JSON object")
    return data


def _to_int(v, key, errors, lo=0, hi=MAX_QTY):
    try:
        if isinstance(v, bool) or v is None or (isinstance(v, float) and not v.is_integer()):
            raise ValueError
        n = int(v)
    except (TypeError, ValueError):
        errors[key] = "must be a whole number"
        return None
    if not lo <= n <= hi:
        errors[key] = f"must be between {lo:,} and {hi:,}"
        return None
    return n


def _commit(message="Conflict", field=None):
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ApiError(message, 409, {field: "already exists"} if field else None)


def _parse_product(data, partial=False):
    errors, out = {}, {}
    if "sku" in data or not partial:
        sku = str(data.get("sku") or "").strip().upper()
        if not sku:
            errors["sku"] = "is required"
        elif len(sku) > 64:
            errors["sku"] = "must be at most 64 characters"
        else:
            out["sku"] = sku
    if "name" in data or not partial:
        name = str(data.get("name") or "").strip()
        if not name:
            errors["name"] = "is required"
        elif len(name) > 120:
            errors["name"] = "must be at most 120 characters"
        else:
            out["name"] = name
    if "description" in data:
        out["description"] = str(data["description"] or "").strip()[:2000]
    for key in ("quantity", "reorder_level"):
        if key in data:
            v = _to_int(data[key], key, errors)
            if v is not None:
                out[key] = v
    if "price" in data:
        try:
            p = Decimal(str(data["price"]).strip())
            if not p.is_finite() or p < 0 or p > MAX_PRICE:
                raise InvalidOperation
            out["price"] = p.quantize(Decimal("0.01"))
        except InvalidOperation:
            errors["price"] = "must be a number between 0 and 9,999,999,999.99"
    if "category_id" in data:
        cid = data["category_id"]
        if cid in (None, ""):
            out["category_id"] = None
        else:
            n = _to_int(cid, "category_id", errors, 1, 2**31 - 1)
            if n is not None:
                if db.session.get(Category, n):
                    out["category_id"] = n
                else:
                    errors["category_id"] = "does not exist"
    if errors:
        raise ApiError("Validation failed", 422, errors)
    return out


def _status_cond(status):
    return {
        "out": Product.quantity <= 0,
        "low": and_(Product.quantity > 0, Product.quantity <= Product.reorder_level),
        "ok": and_(Product.quantity > 0, Product.quantity > Product.reorder_level),
    }.get(status)


def _filtered():
    q = Product.query
    if s := request.args.get("q", "").strip():
        esc = s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like = f"%{esc}%"
        q = q.filter(or_(Product.name.ilike(like, escape="\\"), Product.sku.ilike(like, escape="\\")))
    cid = request.args.get("category_id", type=int)
    if cid is not None:  # 0 = uncategorized
        q = q.filter(Product.category_id.is_(None) if cid == 0 else Product.category_id == cid)
    if status := request.args.get("status"):
        cond = _status_cond(status)
        if cond is None:
            raise ApiError("Invalid status (use ok, low or out)")
        q = q.filter(cond)
    return q


def _sorted(q):
    sort = request.args.get("sort", "-updated_at")
    field = sort.lstrip("-")
    if field not in SORTABLE:
        raise ApiError("Invalid sort field")
    col = getattr(Product, field)
    return q.order_by(col.desc() if sort.startswith("-") else col.asc(), Product.id)


# ---------------------------------------------------------------- products
@bp.get("/products")
def list_products():
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = min(max(request.args.get("per_page", 20, type=int), 1), 100)
    p = _sorted(_filtered()).paginate(page=page, per_page=per_page, error_out=False)
    return jsonify(items=[x.to_dict() for x in p.items], page=p.page, per_page=per_page, total=p.total, pages=p.pages)


@bp.get("/products/export.csv")
def export_csv():
    rows = _sorted(_filtered()).limit(50000).all()

    def safe(v):  # neutralise spreadsheet formula injection
        s = "" if v is None else str(v)
        return "'" + s if s and s[0] in "=+-@\t\r" else s

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["SKU", "Name", "Category", "Quantity", "Reorder level", "Status", "Price", "Stock value"])
    for r in rows:
        w.writerow([safe(r.sku), safe(r.name), safe(r.category.name if r.category else ""), r.quantity,
                    r.reorder_level, r.status, f"{r.price:.2f}", f"{r.price * r.quantity:.2f}"])
    return Response("\ufeff" + buf.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="stockly-products-{date.today()}.csv"'})


@bp.post("/products")
def create_product():
    product = Product(**_parse_product(_json()))
    try:
        db.session.add(product)
        db.session.flush()
        if product.quantity:
            db.session.add(StockMovement(product_id=product.id, change=product.quantity,
                                         quantity_after=product.quantity, reason="Initial stock"))
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ApiError("SKU already exists", 409, {"sku": "already exists"})
    return jsonify(product.to_dict()), 201


@bp.get("/products/<int:pid>")
def get_product(pid):
    return jsonify(db.get_or_404(Product, pid).to_dict())


@bp.route("/products/<int:pid>", methods=["PUT", "PATCH"])
def update_product(pid):
    """PUT requires sku+name, PATCH is partial. Quantity is changed only via /adjust (audit trail)."""
    product = db.get_or_404(Product, pid)
    data = _parse_product(_json(), partial=request.method == "PATCH")
    data.pop("quantity", None)
    for k, v in data.items():
        setattr(product, k, v)
    _commit("SKU already exists", "sku")
    return jsonify(product.to_dict())


@bp.delete("/products/<int:pid>")
def delete_product(pid):
    db.session.delete(db.get_or_404(Product, pid))
    db.session.commit()
    return "", 204


@bp.post("/products/<int:pid>/adjust")
def adjust_stock(pid):
    """Body: {"change": +/-n, "reason": "..."}  or  {"set": n, "reason": "..."} for a stock count."""
    data = _json()
    errors = {}
    if ("change" in data) == ("set" in data):
        raise ApiError("Validation failed", 422, {"change": "provide exactly one of 'change' or 'set'"})
    change = target = None
    if "change" in data:
        change = _to_int(data["change"], "change", errors, -MAX_QTY, MAX_QTY)
        if change == 0:
            errors["change"] = "must not be 0"
    else:
        target = _to_int(data["set"], "set", errors)
    if errors:
        raise ApiError("Validation failed", 422, errors)

    # Lock only the product row (skip the joined category: Postgres can't FOR UPDATE an outer join)
    product = db.session.execute(
        db.select(Product).options(db.lazyload(Product.category))
        .where(Product.id == pid).with_for_update(of=Product)
    ).scalar_one_or_none()
    if not product:
        raise ApiError("Not found", 404)
    if target is not None:
        change = target - product.quantity
        if change == 0:
            raise ApiError("Validation failed", 422, {"set": "matches the current stock"})
    new_qty = product.quantity + change
    if new_qty < 0:
        raise ApiError(f"Insufficient stock (have {product.quantity})", 409)
    if new_qty > MAX_QTY:
        raise ApiError("Quantity would exceed the maximum of 1,000,000,000", 422)
    product.quantity = new_qty
    db.session.add(StockMovement(product_id=pid, change=change, quantity_after=new_qty,
                                 reason=str(data.get("reason") or "").strip()[:200]))
    db.session.commit()
    return jsonify(product.to_dict())


@bp.get("/products/<int:pid>/movements")
def product_movements(pid):
    db.get_or_404(Product, pid)
    limit = min(max(request.args.get("limit", 50, type=int), 1), 200)
    rows = StockMovement.query.filter_by(product_id=pid).order_by(StockMovement.id.desc()).limit(limit).all()
    return jsonify([r.to_dict() for r in rows])


@bp.get("/movements")
def all_movements():
    """Global activity feed, newest first. Cursor pagination: ?before=<id>."""
    limit = min(max(request.args.get("limit", 30, type=int), 1), 100)
    q = (db.session.query(StockMovement, Product.name, Product.sku)
         .join(Product, Product.id == StockMovement.product_id))
    if before := request.args.get("before", type=int):
        q = q.filter(StockMovement.id < before)
    rows = q.order_by(StockMovement.id.desc()).limit(limit + 1).all()
    more, rows = len(rows) > limit, rows[:limit]
    items = [{**m.to_dict(), "product_name": n, "product_sku": s} for m, n, s in rows]
    return jsonify(items=items, has_more=more, next_before=items[-1]["id"] if more else None)


# ---------------------------------------------------------------- categories
def _cat_name(exclude=None):
    name = str(_json().get("name") or "").strip()
    if not name:
        raise ApiError("Validation failed", 422, {"name": "is required"})
    if len(name) > 80:
        raise ApiError("Validation failed", 422, {"name": "must be at most 80 characters"})
    dup = Category.query.filter(func.lower(Category.name) == name.lower())
    if exclude:
        dup = dup.filter(Category.id != exclude)
    if dup.first():
        raise ApiError("Category already exists", 409, {"name": "already exists"})
    return name


@bp.get("/categories")
def list_categories():
    rows = (db.session.query(Category, func.count(Product.id))
            .outerjoin(Product, Product.category_id == Category.id)
            .group_by(Category.id).order_by(func.lower(Category.name)).all())
    return jsonify([c.to_dict(n) for c, n in rows])


@bp.post("/categories")
def create_category():
    c = Category(name=_cat_name())
    db.session.add(c)
    _commit("Category already exists", "name")
    return jsonify(c.to_dict(0)), 201


@bp.route("/categories/<int:cid>", methods=["PUT", "PATCH"])
def update_category(cid):
    c = db.get_or_404(Category, cid)
    c.name = _cat_name(exclude=cid)
    _commit("Category already exists", "name")
    return jsonify(c.to_dict())


@bp.delete("/categories/<int:cid>")
def delete_category(cid):
    db.session.delete(db.get_or_404(Category, cid))  # products become uncategorized (FK SET NULL)
    db.session.commit()
    return "", 204


# ---------------------------------------------------------------- stats / health
@bp.get("/stats")
def stats():
    row = db.session.query(
        func.count(Product.id),
        func.coalesce(func.sum(Product.quantity * Product.price), 0),
        func.coalesce(func.sum(db.case((_status_cond("low"), 1), else_=0)), 0),
        func.coalesce(func.sum(db.case((_status_cond("out"), 1), else_=0)), 0),
    ).one()
    return jsonify(products=row[0], inventory_value=float(row[1]), low_stock=int(row[2]),
                   out_of_stock=int(row[3]), categories=Category.query.count())


@bp.get("/health")
def health():
    db.session.execute(text("SELECT 1"))
    return jsonify(status="ok")
