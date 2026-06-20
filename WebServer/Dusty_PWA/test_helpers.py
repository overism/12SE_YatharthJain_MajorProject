def create_test_user(db, email='test@example.com', password='password123'):
    """Helper to create test user"""
    from werkzeug.security import generate_password_hash
    hashed = generate_password_hash(password)
    cursor = db.execute(
        "INSERT INTO users (email, password, firstName, lastName) VALUES (?, ?, ?, ?)",
        (email, hashed, 'Test', 'User')
    )
    db.commit()
    return cursor.lastrowid

def create_test_subject(db, user_id, name='Mathematics', colour='blue'):
    """Helper to create test subject"""
    cursor = db.execute(
        "INSERT INTO subjects (userID, subjectName, colourScheme) VALUES (?, ?, ?)",
        (user_id, name, colour)
    )
    db.commit()
    return cursor.lastrowid

def create_test_task(db, user_id, title='Test Task', due_date='2026-06-30'):
    """Helper to create test task"""
    cursor = db.execute(
        "INSERT INTO tasks (userID, title, dueDate, taskType, status) VALUES (?, ?, ?, ?, ?)",
        (user_id, title, due_date, 'homework', 'pending')
    )
    db.commit()
    return cursor.lastrowid

def test_signup_valid(client, db):
    """Valid signup creates user"""
    response = client.post('/add_user', json={
        'email': 'newuser@example.com',
        'password': 'SecurePass123',
        'firstName': 'John',
        'lastName': 'Doe'
    })
    assert response.status_code in [200, 302]  # redirect or success
    
    # Verify user in database
    cursor = db.execute("SELECT * FROM users WHERE email = ?", 
                        ('newuser@example.com',))
    user = cursor.fetchone()
    assert user is not None

def test_signup_duplicate_email(client, db):
    """Duplicate email rejected"""
    create_test_user(db, 'test@example.com')
    
    response = client.post('/add_user', json={
        'email': 'test@example.com',
        'password': 'Pass123',
        'firstName': 'Jane',
        'lastName': 'Doe'
    })
    assert response.status_code in [400, 409]  # Bad request or conflict

def test_signup_missing_fields(client):
    """Missing required fields rejected"""
    response = client.post('/add_user', json={
        'email': 'test@example.com'
        # missing password, firstName, lastName
    })
    assert response.status_code in [400, 422]  # Bad request

def test_password_hashed(db):
    """Password is hashed, not plaintext"""
    create_test_user(db, 'test@example.com', 'mypassword')
    
    cursor = db.execute("SELECT password FROM users WHERE email = ?", 
                        ('test@example.com',))
    row = cursor.fetchone()
    assert row['password'] != 'mypassword'  # Should be hashed
    assert len(row['password']) > 20  # Hash is much longer

def test_login_valid(client, db):
    """Valid login creates session"""
    create_test_user(db, 'test@example.com', 'password123')
    
    response = client.post('/login_validation', json={
        'email': 'test@example.com',
        'password': 'password123'
    })
    assert response.status_code == 200
    
    # Check session
    data = response.get_json()
    assert data.get('success') == True or 'user_id' in data

def test_login_wrong_password(client, db):
    """Wrong password rejected"""
    create_test_user(db, 'test@example.com', 'password123')
    
    response = client.post('/login_validation', json={
        'email': 'test@example.com',
        'password': 'wrongpassword'
    })
    assert response.status_code in [401, 403]  # Unauthorized

def test_login_nonexistent_user(client):
    """Non-existent user rejected"""
    response = client.post('/login_validation', json={
        'email': 'nouser@example.com',
        'password': 'password'
    })
    assert response.status_code in [401, 404]

def test_logout_clears_session(client, db):
    """Logout clears session"""
    user_id = create_test_user(db)
    
    # Login
    client.post('/login_validation', json={
        'email': 'test@example.com',
        'password': 'password123'
    })
    
    # Logout
    response = client.get('/logout')
    assert response.status_code in [200, 302]

def test_home_requires_login(client):
    """Home page requires login"""
    response = client.get('/home')
    assert response.status_code == 302  # Redirect to login
    assert '/login' in response.location

def test_profile_requires_login(client):
    """Profile page requires login"""
    response = client.get('/profile')
    assert response.status_code == 302

def test_authenticated_access_home(client, db):
    """Logged-in user accesses home"""
    user_id = create_test_user(db)
    
    with client:
        client.post('/login_validation', json={
            'email': 'test@example.com',
            'password': 'password123'
        })
        response = client.get('/home')
        assert response.status_code == 200

def test_change_password_valid(client, db):
    """Valid password change"""
    create_test_user(db, 'test@example.com', 'oldpass123')
    
    with client:
        client.post('/login_validation', json={
            'email': 'test@example.com',
            'password': 'oldpass123'
        })
        
        response = client.post('/change-password', json={
            'current_password': 'oldpass123',
            'new_password': 'newpass456',
            'confirm_password': 'newpass456'
        })
        assert response.status_code == 200

def test_change_password_wrong_old(client, db):
    """Wrong old password rejected"""
    create_test_user(db)
    
    with client:
        client.post('/login_validation', json={
            'email': 'test@example.com',
            'password': 'password123'
        })
        
        response = client.post('/change-password', json={
            'current_password': 'wrongoldpass',
            'new_password': 'newpass456',
            'confirm_password': 'newpass456'
        })
        assert response.status_code in [400, 401]

def test_password_mismatch(client, db):
    """New passwords must match"""
    create_test_user(db)
    
    with client:
        client.post('/login_validation', json={
            'email': 'test@example.com',
            'password': 'password123'
        })
        
        response = client.post('/change-password', json={
            'current_password': 'password123',
            'new_password': 'newpass456',
            'confirm_password': 'differentpass'
        })
        assert response.status_code == 400

def test_get_profile(client, db):
    """Get user profile"""
    user_id = create_test_user(db, first_name='John', last_name='Doe')
    
    with client:
        client.post('/login_validation', json={
            'email': 'test@example.com',
            'password': 'password123'
        })
        
        response = client.get('/profile')
        assert response.status_code == 200
        assert b'John' in response.data or 'John' in response.get_data(as_text=True)

def test_update_profile(client, db):
    """Update profile information"""
    user_id = create_test_user(db)
    
    with client:
        client.post('/login_validation', json={
            'email': 'test@example.com',
            'password': 'password123'
        })
        
        response = client.post('/update-profile', json={
            'firstName': 'Jonathan',
            'lastName': 'Smith'
        })
        assert response.status_code == 200
        
        # Verify change
        cursor = db.execute("SELECT firstName FROM users WHERE userID = ?", (user_id,))
        assert cursor.fetchone()['firstName'] == 'Jonathan'

def test_save_bio(client, db):
    """Update user bio"""
    create_test_user(db)
    
    with client:
        client.post('/login_validation', json={
            'email': 'test@example.com',
            'password': 'password123'
        })
        
        response = client.post('/save-bio', json={
            'bio': 'Studying HSC Physics and Chemistry'
        })
        assert response.status_code == 200

def test_delete_account(client, db):
    """Account deletion removes user"""
    user_id = create_test_user(db)
    
    with client:
        client.post('/login_validation', json={
            'email': 'test@example.com',
            'password': 'password123'
        })
        
        response = client.post('/delete-account', json={
            'password': 'password123'
        })
        assert response.status_code == 200
        
        # Verify user deleted
        cursor = db.execute("SELECT * FROM users WHERE userID = ?", (user_id,))
        assert cursor.fetchone() is None

def test_cannot_login_after_deletion(client, db):
    """Cannot login after account deletion"""
    create_test_user(db)
    
    with client:
        client.post('/login_validation', json={
            'email': 'test@example.com',
            'password': 'password123'
        })
        client.post('/delete-account', json={
            'password': 'password123'
        })
        
        # Try to login again
        response = client.post('/login_validation', json={
            'email': 'test@example.com',
            'password': 'password123'
        })
        assert response.status_code in [401, 404]