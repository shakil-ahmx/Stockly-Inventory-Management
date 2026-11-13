import click
from . import db
from .models import Category, Product, StockMovement


def register(app):
    @app.cli.command("seed")
    def seed():
        """Load sample data: flask --app run seed"""
        if Product.query.first():
            click.echo("Data already present.")
            return
        cats = {n: Category(name=n) for n in ("Electronics", "Office", "Furniture", "Accessories")}
        db.session.add_all(cats.values())
        db.session.flush()
        items = [
            ("EL-1001", "Wireless Mouse", "Electronics", 120, 24.99, 20),
            ("EL-1002", "Mechanical Keyboard", "Electronics", 8, 89.00, 15),
            ("OF-2001", "A4 Paper (500 sheets)", "Office", 300, 5.49, 50),
            ("OF-2002", "Gel Pens (12 pack)", "Office", 0, 7.25, 25),
            ("FU-3001", "Ergonomic Chair", "Furniture", 14, 219.00, 5),
            ("AC-4001", "USB-C Cable 2m", "Accessories", 65, 9.99, 30),
        ]
        for sku, name, cat, qty, price, rl in items:
            p = Product(sku=sku, name=name, category_id=cats[cat].id, quantity=qty, price=price, reorder_level=rl)
            db.session.add(p)
            db.session.flush()
            if qty:
                db.session.add(StockMovement(product_id=p.id, change=qty, quantity_after=qty, reason="Initial stock"))
        db.session.commit()
        click.echo("Seeded sample data.")
