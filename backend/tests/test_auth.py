import pytest

def test_auth_flow(client):
    test_email = "testuser@leadradar.com"
    test_password = "password123"
    
    # 1. Test Registration
    reg_response = client.post("/auth/register", json={
        "email": test_email,
        "password": test_password,
        "full_name": "Test User"
    })
    assert reg_response.status_code == 200, f"Registration failed: {reg_response.text}"
    token_data = reg_response.json()
    assert "access_token" in token_data
    token = token_data["access_token"]
    
    # 2. Test Registration duplicate email block
    dup_response = client.post("/auth/register", json={
        "email": test_email,
        "password": "anotherpassword",
        "full_name": "Duplicate User"
    })
    assert dup_response.status_code == 400
    
    # 3. Test Profile Fetch (/auth/me)
    headers = {"Authorization": f"Bearer {token}"}
    me_response = client.get("/auth/me", headers=headers)
    assert me_response.status_code == 200, f"Fetch profile failed: {me_response.text}"
    me_data = me_response.json()
    assert me_data["email"] == test_email
    assert me_data["full_name"] == "Test User"
    
    # 4. Test Login
    login_response = client.post("/auth/login", json={
        "email": test_email,
        "password": test_password
    })
    assert login_response.status_code == 200
    login_token_data = login_response.json()
    assert "access_token" in login_token_data
    
    # 5. Test Invalid Login
    invalid_login = client.post("/auth/login", json={
        "email": test_email,
        "password": "wrong_password"
    })
    assert invalid_login.status_code == 401
