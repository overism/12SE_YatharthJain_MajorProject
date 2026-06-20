import pytest
import os
import sqlite3
from app import app

@pytest.fixture
def client():
    """Create test client with test database"""
    app.config['TESTING'] = True
    app.config['DATABASE'] = 'test_dusty.db'
    app.config['SECRET_KEY'] = 'test-secret-key'
    
    with app.app_context():
        yield app.test_client()

@pytest.fixture
def db():
    """Create fresh test database for each test"""
    if os.path.exists('test_dusty.db'):
        os.remove('test_dusty.db')
    
    conn = sqlite3.connect('test_dusty.db')
    conn.row_factory = sqlite3.Row
    
    with open('static/db/schema.sql', 'r') as f:
        conn.executescript(f.read())
    conn.commit()
    
    yield conn
    conn.close()
    
    if os.path.exists('test_dusty.db'):
        os.remove('test_dusty.db')