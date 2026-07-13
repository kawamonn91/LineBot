import requests
import base64

headers = {"Authorization": "Client-ID 546c25a59c58ad7"}
with open("/home/toya/LineBot/data/images/test.jpg", "wb") as f:
    f.write(b"test image")

# Try to upload a dummy or maybe a real small image
