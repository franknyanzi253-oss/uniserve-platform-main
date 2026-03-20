import requests

BASE_URL = 'http://127.0.0.1:5000'

s1 = requests.Session()
s2 = requests.Session()

# 1. Register users
r = s1.post(f"{BASE_URL}/register", data={
    "name": "Provider User",
    "email": "provider@uict.ac.ug",
    "password": "password123",
    "user_type": "provider"
})
print("Provider register:", r.status_code)

r = s2.post(f"{BASE_URL}/register", data={
    "name": "Seeker User",
    "email": "seeker@student.uict.ac.ug",
    "password": "password123",
    "user_type": "seeker"
})
print("Seeker register:", r.status_code)

# 2. Login
s1.post(f"{BASE_URL}/login", data={"email": "provider@uict.ac.ug", "password": "password123"})
s2.post(f"{BASE_URL}/login", data={"email": "seeker@student.uict.ac.ug", "password": "password123"})

# 3. Add Service (Provider)
r = s1.post(f"{BASE_URL}/add_service", data={
    "title": "Math Tutoring",
    "description": "I teach math.",
    "category": "Tutoring",
    "price": "50000 UGX",
    "location": "Kampala",
    "contact_info": "12345678"
})
print("Add Service:", r.status_code)

# 4. Dashboard (Provider)
r = s1.get(f"{BASE_URL}/dashboard")
print("Provider Dashboard:", r.status_code)

# 5. Services List (Seeker)
r = s2.get(f"{BASE_URL}/services")
print("Services list:", r.status_code)

# Find service ID
# For simplicity, let's assume it's 1
service_id = 1

# 6. Request Service (Seeker)
r = s2.post(f"{BASE_URL}/request_service", data={
    "service_id": service_id,
    "message": "I need math help."
})
print("Request Service:", r.status_code)

# 7. Service Requests (Provider)
r = s1.get(f"{BASE_URL}/service_requests")
print("Provider Service Requests:", r.status_code)

# 8. Update Request Status (Provider)
r = s1.post(f"{BASE_URL}/update_request_status/1", data={"status": "accepted"})
print("Update Request:", r.status_code)

# 9. Messages
r = s1.post(f"{BASE_URL}/messages/2", data={"content": "Hello Seeker"})
print("Send Message:", r.status_code)
r = s2.get(f"{BASE_URL}/messages/1")
print("Read Message:", r.status_code)

# 10. Reviews
r = s2.post(f"{BASE_URL}/add_review/1", data={"rating": 5, "comment": "Great tutor!", "service_id": 1})
print("Add Review:", r.status_code)

r = s2.get(f"{BASE_URL}/profile/1")
print("View Profile:", r.status_code)

