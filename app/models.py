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
        return any(role.name == role_name for role in self.roles)

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
    critical_stock_level = db.Column(db.Float, nullable=False, default=0)
    batches = db.relationship('RawMaterialBatch', backref='material', lazy=True, cascade="all, delete-orphan")

class RawMaterialBatch(db.Model):
    __tablename__ = 'raw_material_batches'
    id = db.Column(db.Integer, primary_key=True)
    raw_material_id = db.Column(db.Integer, db.ForeignKey('raw_materials.id'), nullable=False)
    batch_number = db.Column(db.String(100), nullable=False)
    quantity_on_hand = db.Column(db.Float, nullable=False, default=0.0)
    unit = db.Column(db.String(20), nullable=False)
    received_date = db.Column(db.Date, nullable=False, default=date.today)

class FinishedProductCategory(db.Model):
    __tablename__ = 'finished_product_categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    finished_products = db.relationship('FinishedProduct', backref='category', lazy=True)

class PackagingCategory(db.Model):
    __tablename__ = 'packaging_categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    packaging_items = db.relationship('Packaging', backref='category', lazy=True, order_by='Packaging.quantity_in_stock')
    __table_args__ = (db.UniqueConstraint('name', name='uq_packaging_categories_name'),)

class Packaging(db.Model):
    __tablename__ = 'packaging'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('packaging_categories.id'), nullable=True)
    quantity_in_stock = db.Column(db.Integer, nullable=False, default=0)
    critical_stock_level = db.Column(db.Integer, nullable=False, default=0)
    products = db.relationship('ProductPackaging', back_populates='packaging')
    __table_args__ = (db.UniqueConstraint('name', name='uq_packaging_name'),)

class ProductPackaging(db.Model):
    __tablename__ = 'product_packaging'
    id = db.Column(db.Integer, primary_key=True)
    finished_product_id = db.Column(db.Integer, db.ForeignKey('finished_products.id'), nullable=False)
    packaging_id = db.Column(db.Integer, db.ForeignKey('packaging.id'), nullable=False)
    quantity_required = db.Column(db.Integer, nullable=False, default=1)
    product = db.relationship('FinishedProduct', back_populates='packaging_bill')
    packaging = db.relationship('Packaging', back_populates='products')

class FinishedProduct(db.Model):
    __tablename__ = 'finished_products'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)
    product_code = db.Column(db.String(50), nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey('finished_product_categories.id'), nullable=True)
    packaging_weight_kg = db.Column(db.Float, nullable=False, default=1.0)
    unit = db.Column(db.String(10), nullable=False, server_default='szt.')
    quantity_in_stock = db.Column(db.Integer, nullable=False, default=0)
    recipe_components = db.relationship('RecipeComponent', foreign_keys='RecipeComponent.finished_product_id', back_populates='product', lazy='dynamic', cascade="all, delete-orphan")
    production_orders = db.relationship('ProductionOrder', back_populates='finished_product', cascade="all, delete-orphan")
    packaging_bill = db.relationship('ProductPackaging', back_populates='product', lazy='dynamic', cascade="all, delete-orphan")

class RecipeComponent(db.Model):
    __tablename__ = 'recipe_components'
    id = db.Column(db.Integer, primary_key=True)
    finished_product_id = db.Column(db.Integer, db.ForeignKey('finished_products.id'), nullable=False)
    raw_material_id = db.Column(db.Integer, db.ForeignKey('raw_materials.id'), nullable=True)
    sub_product_id = db.Column(db.Integer, db.ForeignKey('finished_products.id'), nullable=True)
    quantity_required = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(10), nullable=False, server_default='kg')
    product = db.relationship('FinishedProduct', foreign_keys=[finished_product_id], back_populates='recipe_components')
    raw_material = db.relationship('RawMaterial')
    sub_product = db.relationship('FinishedProduct', foreign_keys=[sub_product_id])
    __table_args__ = (
        db.CheckConstraint(
            '(raw_material_id IS NOT NULL AND sub_product_id IS NULL) OR (raw_material_id IS NULL AND sub_product_id IS NOT NULL)',
            name='chk_recipe_component_type'
        ),
    )

class ProductionOrder(db.Model):
    __tablename__ = 'production_orders'
    id = db.Column(db.Integer, primary_key=True)
    finished_product_id = db.Column(db.Integer, db.ForeignKey('finished_products.id'), nullable=False)
    planned_quantity = db.Column(db.Integer, nullable=False, default=0)
    quantity_produced = db.Column(db.Integer, nullable=False, default=0)
    order_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    sample_required = db.Column(db.Boolean, nullable=False, default=False)
    finished_product = db.relationship('FinishedProduct', back_populates='production_orders')
    consumption_log = db.relationship('ProductionLog', foreign_keys='ProductionLog.production_order_id', backref='production_order', lazy=True, cascade="all, delete-orphan")
    @property
    def production_date(self):
        return self.order_date.date()

class ProductionLog(db.Model):
    __tablename__ = 'production_logs'
    id = db.Column(db.Integer, primary_key=True)
    production_order_id = db.Column(db.Integer, db.ForeignKey('production_orders.id'), nullable=False)
    raw_material_batch_id = db.Column(db.Integer, db.ForeignKey('raw_material_batches.id'), nullable=True)
    sub_product_order_id = db.Column(db.Integer, db.ForeignKey('production_orders.id'), nullable=True)
    quantity_consumed = db.Column(db.Float, nullable=False)
    batch = db.relationship('RawMaterialBatch', lazy=True)
    consumed_from_order = db.relationship('ProductionOrder', foreign_keys=[sub_product_order_id])

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

class VacationRequest(db.Model):
    __tablename__ = 'vacation_requests'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    request_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    status = db.Column(db.String(50), nullable=False, default='Oczekuje')
    notes = db.Column(db.Text, nullable=True)
    admin_notes = db.Column(db.Text, nullable=True)
    user = db.relationship('User', backref='vacation_requests')

class SalesReportLog(db.Model):
    __tablename__ = 'sales_report_logs'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('finished_products.id'), nullable=False)
    report_date = db.Column(db.Date, nullable=False)
    quantity_sold = db.Column(db.Integer, nullable=False)
    product = db.relationship('FinishedProduct')
    
class ActivityLog(db.Model):
    __tablename__ = 'activity_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    action = db.Column(db.Text, nullable=False)
    url = db.Column(db.String(255), nullable=True)  # Opcjonalny link do obiektu

    user = db.relationship('User', backref='activity_logs')

    def __repr__(self):
        return f'<ActivityLog {self.user.username}: {self.action[:50]}>'