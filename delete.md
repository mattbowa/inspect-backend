curl -X POST http://localhost:8000/scans \
 -H "Content-Type: application/json" \
 -d '{"url": "https://www.petstock.com.au/", "max_pages": 2}'

curl http://localhost:8000/scans/71628959-9cc4-4812-a732-0d7ca1cfe6df/status

curl http://localhost:8000/reports/4228bc1f-782c-480b-8292-0c6c7978c45b | python3 -m json.tool

is deeply involved in thinking
through a project, I want to work alone in peace

VALUE
Clear, direct communication
Ownership & accountability
Reliability (do what you say)
Efficiency (no unnecessary meetings)
Openness to feedback
Team collaboration
DO (what you want people to do)
Be direct and honest with me
Send clear, concise messages (especially async)
Flag blockers early
Ask questions instead of assuming
Give feedback privately and constructively
Provide context when assigning tasks
DON’T (what you don’t want)
Don’t micromanage
Don’t wait until the last minute to raise issues
Don’t overcomplicate simple things
Don’t schedule unnecessary meetings
Don’t give vague instructions
Don’t overload with too many options without a recommendation
