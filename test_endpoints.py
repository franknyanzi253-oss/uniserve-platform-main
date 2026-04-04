import urllib.request
import urllib.parse
import http.cookiejar

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

BASE_URL = 'http://127.0.0.1:5000'

def request(method, path, data=None):
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, method=method)
    if data is not None:
        data = urllib.parse.urlencode(data).encode()
        req.add_header('Content-Type', 'application/x-www-form-urlencoded')
    
    try:
        resp = opener.open(req, data=data)
        return resp.status
    except urllib.error.HTTPError as e:
        print(f"Error {e.code} on {method} {path}")
        return e.code
    except Exception as e:
        print(f"Exception on {method} {path}: {e}")
        return None

print("GET / :", request('GET', '/'))
print("POST /register (Provider):", request('POST', '/register', {
    "name": "Provider",
    "email": "provider1@student.uict.ac.ug",
    "password": "pass",
    "user_type": "provider"
}))
print("POST /login :", request('POST', '/login', {
    "email": "provider1@student.uict.ac.ug",
    "password": "pass"
}))
print("GET /dashboard :", request('GET', '/dashboard'))
print("POST /add_service :", request('POST', '/add_service', {
    "title": "Fix PC",
    "description": "I fix laptops",
    "category": "Computer Repair",
    "price": "Free",
    "location": "Hostel",
    "contact_info": "0000"
}))
print("GET /services :", request('GET', '/services'))
print("POST /logout :", request('GET', '/logout'))

# Seeker
print("POST /register (Seeker):", request('POST', '/register', {
    "name": "Seeker",
    "email": "seeker1@student.uict.ac.ug",
    "password": "pass",
    "user_type": "seeker"
}))
print("POST /login :", request('POST', '/login', {
    "email": "seeker1@student.uict.ac.ug",
    "password": "pass"
}))
print("GET /dashboard (Seeker) :", request('GET', '/dashboard'))
print("POST /request_service :", request('POST', '/request_service', {
    "service_id": "1",
    "message": "Help me"
}))
print("POST /add_review :", request('POST', '/add_review/1', {
    "rating": "5",
    "comment": "Good",
    "service_id": "1"
}))
print("GET /profile/1 :", request('GET', '/profile/1'))
print("POST /messages/1 :", request('POST', '/messages/1', {
    "content": "Hi there"
}))
print("GET /messages :", request('GET', '/messages'))
