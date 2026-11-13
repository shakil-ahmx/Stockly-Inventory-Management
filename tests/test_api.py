import os
import pytest
from app import create_app, db


@pytest.fixture()
def client():
    uri = os.getenv("TEST_DATABASE_URL", "sqlite://")
    app = create_app({"SQLALCHEMY_DATABASE_URI": uri, "TESTING": True})
    with app.app_context():
        db.drop_all(); db.create_all()
        yield app.test_client()
        db.session.remove(); db.drop_all()


def mk(c, sku="a1", name="Widget", **kw):
    r = c.post("/api/products", json={"sku": sku, "name": name, **kw})
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def test_crud_and_normalisation(client):
    p = mk(client, price=2.5, quantity=5)
    assert p["sku"] == "A1" and p["status"] == "low" and p["value"] == 12.5
    assert client.post("/api/products", json={"sku": "A1", "name": "Dup"}).get_json()["details"]["sku"]
    assert client.put(f"/api/products/{p['id']}", json={"sku": "A1", "name": "Gadget", "quantity": 999}).get_json()["quantity"] == 5
    assert client.patch(f"/api/products/{p['id']}", json={"price": "3"}).get_json()["price"] == 3.0
    assert client.delete(f"/api/products/{p['id']}").status_code == 204
    assert client.get(f"/api/products/{p['id']}").status_code == 404


def test_adjust_modes_and_limits(client):
    p = mk(client, quantity=5, reorder_level=2)
    url = f"/api/products/{p['id']}/adjust"
    assert client.post(url, json={"change": -2}).get_json()["quantity"] == 3
    assert client.post(url, json={"change": -99}).status_code == 409
    assert client.post(url, json={"set": 40, "reason": "count"}).get_json()["quantity"] == 40
    assert client.post(url, json={"set": 40}).status_code == 422
    assert client.post(url, json={"change": 0}).status_code == 422
    assert client.post(url, json={}).status_code == 422
    assert client.post(url, json={"change": 1, "set": 1}).status_code == 422
    assert client.post(url, json={"change": 1_000_000_000}).status_code == 422
    moves = client.get(f"/api/products/{p['id']}/movements").get_json()
    assert [m["change"] for m in moves] == [37, -2, 5]


def test_filters_status_search_stats(client):
    cat = client.post("/api/categories", json={"name": "Tools"}).get_json()
    mk(client, "ok1", "Hammer", quantity=50, reorder_level=5, category_id=cat["id"])
    mk(client, "low1", "Nails 100%", quantity=3, reorder_level=5)
    mk(client, "out1", "Saw", quantity=0)
    g = lambda q: client.get("/api/products?" + q).get_json()
    assert g("status=ok")["total"] == 1 and g("status=low")["total"] == 1 and g("status=out")["total"] == 1
    assert g("category_id=0")["total"] == 2 and g(f"category_id={cat['id']}")["total"] == 1
    assert g("q=100%25")["total"] == 1 and g("q=%25")["total"] == 1   # % is literal, not a wildcard
    assert g("sort=-price&per_page=2")["per_page"] == 2
    assert client.get("/api/products?sort=evil").status_code == 400
    assert client.get("/api/products?status=zzz").status_code == 400
    s = client.get("/api/stats").get_json()
    assert (s["products"], s["low_stock"], s["out_of_stock"]) == (3, 1, 1)
    assert client.get("/api/categories").get_json()[0]["product_count"] == 1


def test_categories(client):
    c = client.post("/api/categories", json={"name": "Toys"}).get_json()
    assert client.post("/api/categories", json={"name": "toys"}).status_code == 409
    assert client.put(f"/api/categories/{c['id']}", json={"name": "Toys"}).status_code == 200
    assert client.put(f"/api/categories/{c['id']}", json={"name": " "}).status_code == 422
    assert client.delete(f"/api/categories/{c['id']}").status_code == 204


def test_validation(client):
    r = client.post("/api/products", json={"sku": "", "price": -1, "quantity": 1.5, "category_id": 99})
    d = r.get_json()["details"]
    assert r.status_code == 422 and {"sku", "name", "price", "quantity", "category_id"} <= set(d)
    assert client.post("/api/products", json={"sku": "x", "name": "y", "price": "1e20"}).status_code == 422
    assert client.post("/api/products", data="nope").status_code == 400


def test_export_feed_health_errors(client):
    mk(client, "=cmd", "=evil", quantity=2)
    csv_text = client.get("/api/products/export.csv").get_data(as_text=True)
    assert "'=CMD" in csv_text and "'=evil" in csv_text
    feed = client.get("/api/movements?limit=1").get_json()
    assert feed["items"][0]["product_name"] == "=evil"
    assert client.get("/api/health").get_json()["status"] == "ok"
    r = client.get("/api/nope"); assert r.status_code == 404 and r.is_json
    assert client.get("/").status_code == 200
