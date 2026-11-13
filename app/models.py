from datetime import datetime, timezone
from . import db


def utcnow():
    return datetime.now(timezone.utc)


def iso(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


class Category(db.Model):
    __tablename__ = "categories"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    def to_dict(self, product_count=None):
        d = {"id": self.id, "name": self.name}
        if product_count is not None:
            d["product_count"] = product_count
        return d


class Product(db.Model):
    __tablename__ = "products"
    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(64), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False, index=True)
    description = db.Column(db.Text, default="")
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id", ondelete="SET NULL"), index=True)
    quantity = db.Column(db.Integer, nullable=False, default=0)
    price = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    reorder_level = db.Column(db.Integer, nullable=False, default=10)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, index=True)

    category = db.relationship("Category", lazy="joined")
    __table_args__ = (
        db.CheckConstraint("quantity >= 0", name="ck_qty_nonneg"),
        db.CheckConstraint("price >= 0", name="ck_price_nonneg"),
        db.CheckConstraint("reorder_level >= 0", name="ck_reorder_nonneg"),
    )

    @property
    def status(self):
        if self.quantity <= 0:
            return "out"
        return "low" if self.quantity <= self.reorder_level else "ok"

    def to_dict(self):
        return {
            "id": self.id,
            "sku": self.sku,
            "name": self.name,
            "description": self.description or "",
            "category": self.category.to_dict() if self.category else None,
            "quantity": self.quantity,
            "price": float(self.price),
            "value": float(self.price * self.quantity),
            "reorder_level": self.reorder_level,
            "status": self.status,
            "created_at": iso(self.created_at),
            "updated_at": iso(self.updated_at),
        }


class StockMovement(db.Model):
    __tablename__ = "stock_movements"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    change = db.Column(db.Integer, nullable=False)
    quantity_after = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(200), default="")
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "product_id": self.product_id,
            "change": self.change,
            "quantity_after": self.quantity_after,
            "reason": self.reason or "",
            "created_at": iso(self.created_at),
        }
