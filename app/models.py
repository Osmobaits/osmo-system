# app/models.py
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date
from flask_login import UserMixin

db = SQLAlchemy()

# === TABELE POŚREDNICZĄCE ===
user_roles = db.Table('user_roles',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('role_id', db.Integer, db.ForeignKey('roles.id'), primary_key=True)
)

task_assignees = db.Table('task_assignees',
    db.Column('task_id', db.Integer, db.ForeignKey('tasks.id'), primary_key=True),
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True)
)

# === MODELE GŁÓWNE ===
class Role(db.Model):
    __tablename__ = 'roles'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)

class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    roles = db.relationship('Role', secondary=user_roles, lazy='subquery',
                            backref=db.backref('users', lazy=True))
    assigned_tasks = db.relationship('Task', secondary=task_assignees, lazy='subquery',
                                     backref=db.backref('assignees', lazy=True))

    def has_role(self, role_name):
        return any(role.name == role.name for role in self.roles)

class Task(db.Model):
    __tablename__ = 'tasks'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    creation_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    priority = db.Column(db.Integer, nullable=False, default=1) 
    due_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(50), nullable=False, default='Nowe')
    assigner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    assigner = db.relationship('User', foreign_keys=[assigner_id], backref='created_tasks')
    attachments = db.relationship('TaskAttachment', backref='task', lazy=True, cascade="all, delete-orphan")

class TaskAttachment(db.Model):
    __tablename__ = 'task_attachments'
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    filepath = db.Column(db.String(255), nullable=False)

class Category(db.Model):
    __tablename__ = 'categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    raw_materials = db.relationship('RawMaterial', backref='category', lazy=True)

class RawMaterial(db.Model):
    __tablename__ = 'raw_materials'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    batches = db.relationship('RawMaterialBatch', backref='material', lazy=True, cascade="all, delete-orphan")

class RawMaterialBatch(db.Model):
    __tablename__ = 'raw_material_batches'
    id = db.Column(db.Integer, primary_key=True)
    raw_material_id = db.Column(db.Integer, db.ForeignKey('raw_materials.id'), nullable=False)
    batch_number = db.Column(db.String(100), nullable=False)
    quantity_on_hand = db.Column(db.Float, nullable=False, default=0.0)
    unit = db.Column(db.String(20), nullable=False)
    received_date = db.Column(db.Date, nullable=False, default=date.today)

class FinishedProduct(db.Model):
    __tablename__ = 'finished_products'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)
    packaging_weight_kg = db.Column(db.Float, nullable=False, default=1.0)
    quantity_in_stock = db.Column(db.Integer, nullable=False, default=0)
    recipe_components = db.relationship('RecipeComponent', backref='finished_product', lazy=True, cascade="all, delete-orphan")
    production_orders = db.relationship('ProductionOrder', back_populates='finished_product', cascade="all, delete-orphan")

class RecipeComponent(db.Model):
    __tablename__ = 'recipe_components'
    id = db.Column(db.Integer, primary_key=True)
    finished_product_id = db.Column(db.Integer, db.ForeignKey('finished_products.id'), nullable=False)
    raw_material_id = db.Column(db.Integer, db.ForeignKey('raw_materials.id'), nullable=False)
    quantity_required = db.Column(db.Float, nullable=False)
    raw_material = db.relationship('RawMaterial', lazy=True)

class ProductionOrder(db.Model):
    __tablename__ = 'production_orders'
    id = db.Column(db.Integer, primary_key=True)
    finished_product_id = db.Column(db.Integer, db.ForeignKey('finished_products.id'), nullable=False)
    quantity_produced = db.Column(db.Integer, nullable=False)
    order_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    finished_product = db.relationship('FinishedProduct', back_populates='production_orders')
    @property
    def production_date(self):
        return self.order_date.date()

class Client(db.Model):
    __tablename__ = 'clients'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)
    orders = db.relationship('Order', backref='client', lazy=True, cascade="all, delete-orphan")
    products = db.relationship('ClientProduct', backref='client_ref', lazy=True, cascade="all, delete-orphan")

class ClientProduct(db.Model):
    __tablename__ = 'client_products'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    product_name = db.Column(db.String(150), nullable=False)

class Order(db.Model):
    __tablename__ = 'orders'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    order_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    is_archived = db.Column(db.Boolean, nullable=False, default=False)
    invoice_number = db.Column(db.String(100), nullable=True)
    products_in_order = db.relationship('OrderProduct', backref='order', lazy=True, cascade="all, delete-orphan")

class OrderProduct(db.Model):
    __tablename__ = 'order_products'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    product_name = db.Column(db.String(150), nullable=False)
    quantity_ordered = db.Column(db.Integer, nullable=False)
    quantity_packed = db.Column(db.Integer, nullable=False, default=0)
    quantity_wykulane = db.Column(db.Integer, nullable=False, default=0)