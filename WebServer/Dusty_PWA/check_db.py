import sqlite3

conn = sqlite3.connect('dusty.db')
cursor = conn.cursor()

# Check Google credentials with all fields
cursor.execute('SELECT * FROM google_creds')
creds = cursor.fetchall()
print(f'Google credentials records: {len(creds)}')
for cred in creds:
    print(f'Full record: {cred}')

# Check users table
cursor.execute('SELECT userID, userName FROM users')
users = cursor.fetchall()
print(f'Users in database: {users}')

# Check tasks table
cursor.execute('SELECT * FROM tasks')
tasks = cursor.fetchall()
print(f'Tasks in database: {len(tasks)}')
for task in tasks:
    print(f'Task: {task}')

# Check subjects table
cursor.execute('SELECT * FROM subjects')
subjects = cursor.fetchall()
print(f'Subjects in database: {len(subjects)}')
for subject in subjects:
    print(f'Subject: {subject}')

conn.close()