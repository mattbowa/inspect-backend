curl -X POST http://localhost:8000/scans \
 -H "Content-Type: application/json" \
 -d '{"url": "https://www.petstock.com.au/", "max_pages": 2}'

curl http://localhost:8000/scans/71628959-9cc4-4812-a732-0d7ca1cfe6df/status

curl http://localhost:8000/reports/9a339085-1377-4dfe-a3cc-f768aafb9d2d | python3 -m json.tool
