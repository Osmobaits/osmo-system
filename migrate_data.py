# migrate_data.py
import os
from sqlalchemy import create_engine, Table, Column, Integer, String, Float, DateTime, Boolean, Date, Text, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, backref
from datetime import datetime, date
from flask_bcrypt import Bcrypt

# --- KONFIGURACJA ---
OLD_DB_URL = "postgresql://osmo_system_user:HrHuTCG81c3pdXFpEfx2yndSqXzRqIuK@dpg-d2h0phggjchc73bma6ag-a.frankfurt-postgres.render.com/osmo_system"
NEW_DB_URL = "postgresql://osmo_system_v2_user:oeuml24m2pIKcF9JK4OJ7BqddwjVu1RA@dpg-d31ub4vdiees738a0900-a.frankfurt-postgres.render.com/osmo_system_v2" # <-- WSTAW TUTAJ POPRAWNY ADRES!

# --- DEFINICJE MODELI DLA STAREJ BAZY DANYCH ---
OldBase = declarative_base()

class OldUser(OldBase):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False)
    password_hash = Column(String(120), nullable=False) # POPRAWKA

class OldClient(OldBase):
    __tablename__ = 'clients'
    id = Column(Integer, primary_key=True)
    name = Column(String(150), unique=True, nullable=False)

class OldOrder(OldBase):
    __tablename__ = 'orders'
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey('clients.id'), nullable=False)
    order_date = Column(DateTime, default=datetime.utcnow)
    is_archived = Column(Boolean, default=False)
    invoice_number = Column(String(100))

class OldClientProduct(OldBase):
    __tablename__ = 'client_products'
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey('clients.id'), nullable=False)
    name = Column(String(150), nullable=False)

class OldOrderProduct(OldBase):
    __tablename__ = 'order_products'
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey('orders.id'), nullable=False)
    product_name = Column(String(150), nullable=False)
    quantity_ordered = Column(Integer, nullable=False)
    quantity_packed = Column(Integer, nullable=False, default=0)
    quantity_wykulane = Column(Integer, nullable=False, default=0)

# --- DEFINICJE MODELI DLA NOWEJ BAZY DANYCH ---
NewBase = declarative_base()

user_roles = Table('user_roles', NewBase.metadata,
    Column('user_id', Integer, ForeignKey('users.id'), primary_key=True),
    Column('role_id', Integer, ForeignKey('roles.id'), primary_key=True)
)

class NewRole(NewBase):
    __tablename__ = 'roles'
    id = Column(Integer, primary_key=True)
    name = Column(String(80), unique=True, nullable=False)

class NewUser(NewBase):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False)
    password_hash = Column(String(128), nullable=False)
    email = Column(String(120), unique=True, nullable=True)
    roles = relationship('NewRole', secondary=user_roles, lazy='subquery',
                            backref=backref('users', lazy=True))

class NewClient(NewBase):
    __tablename__ = 'clients'
    id = Column(Integer, primary_key=True)
    name = Column(String(150), unique=True, nullable=False)
    orders = relationship('NewOrder', backref='client', lazy=True, cascade="all, delete-orphan")
    products = relationship('NewClientProduct', backref='client_ref', lazy=True, cascade="all, delete-orphan")

class NewOrder(NewBase):
    __tablename__ = 'orders'
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey('clients.id'), nullable=False)
    order_date = Column(DateTime, nullable=False, default=datetime.utcnow)
    is_archived = Column(Boolean, nullable=False, default=False)
    invoice_number = Column(String(100), nullable=True)
    products_in_order = relationship('NewOrderProduct', backref='order', lazy=True, cascade="all, delete-orphan")

class NewClientProduct(NewBase):
    __tablename__ = 'client_products'
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey('clients.id'), nullable=False)
    product_name = Column(String(150), nullable=False)

class NewOrderProduct(NewBase):
    __tablename__ = 'order_products'
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey('orders.id'), nullable=False)
    product_name = Column(String(150), nullable=False)
    quantity_ordered = Column(Integer, nullable=False)
    quantity_packed = Column(Integer, nullable=False, default=0)
    quantity_wykulane = Column(Integer, nullable=False, default=0)

# --- SKRYPT MIGRACYJNY ---
def migrate():
    old_engine = create_engine(OLD_DB_URL)
    new_engine = create_engine(NEW_DB_URL)
    OldSession = sessionmaker(bind=old_engine)
    NewSession = sessionmaker(bind=new_engine)
    old_session = OldSession()
    new_session = NewSession()
    bcrypt = Bcrypt()

    print("Rozpoczynanie migracji...")

    # Migracja Użytkowników
    print("Migracja użytkowników...")
    old_users = old_session.query(OldUser).all()
    for old_user in old_users:
        new_user = NewUser(
            username=old_user.username,
            password_hash=old_user.password_hash, # POPRAWKA
            email=f"{old_user.username}@example.com"
        )
        new_session.add(new_user)
    new_session.commit()
    print(f"Przeniesiono {len(old_users)} użytkowników.")

    # Migracja Klientów
    print("Migracja klientów...")
    old_clients = old_session.query(OldClient).all()
    client_id_map = {}
    for old_client in old_clients:
        new_client = NewClient(name=old_client.name)
        new_session.add(new_client)
        new_session.flush()
        client_id_map[old_client.id] = new_client.id
    new_session.commit()
    print(f"Przeniesiono {len(old_clients)} klientów.")

    # Migracja Produktów Dedykowanych
    print("Migracja produktów dedykowanych...")
    old_client_products = old_session.query(OldClientProduct).all()
    for old_product in old_client_products:
        new_client_id = client_id_map.get(old_product.client_id)
        if new_client_id:
            new_product = NewClientProduct(
                client_id=new_client_id,
                product_name=old_product.name
            )
            new_session.add(new_product)
    new_session.commit()
    print(f"Przeniesiono {len(old_client_products)} produktów dedykowanych.")
    
    # Migracja Zamówień
    print("Migracja zamówień...")
    old_orders = old_session.query(OldOrder).all()
    order_id_map = {}
    for old_order in old_orders:
        new_client_id = client_id_map.get(old_order.client_id)
        if new_client_id:
            new_order = NewOrder(
                client_id=new_client_id,
                order_date=old_order.order_date,
                is_archived=old_order.is_archived,
                invoice_number=old_order.invoice_number
            )
            new_session.add(new_order)
            new_session.flush()
            order_id_map[old_order.id] = new_order.id
    new_session.commit()
    print(f"Przeniesiono {len(old_orders)} zamówień.")

    # Migracja Produktów w Zamówieniach
    print("Migracja produktów w zamówieniach...")
    old_order_products = old_session.query(OldOrderProduct).all()
    for old_item in old_order_products:
        new_order_id = order_id_map.get(old_item.order_id)
        if new_order_id:
            new_item = NewOrderProduct(
                order_id=new_order_id,
                product_name=old_item.product_name,
                quantity_ordered=old_item.quantity_ordered,
                quantity_packed=old_item.quantity_packed,
                quantity_wykulane=old_item.quantity_wykulane
            )
            new_session.add(new_item)
    new_session.commit()
    print(f"Przeniesiono {len(old_order_products)} pozycji w zamówieniach.")
    
    print("Migracja zakończona pomyślnie!")

if __name__ == '__main__':
    migrate()