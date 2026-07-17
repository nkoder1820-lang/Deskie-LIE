import sqlite3, json

conn = sqlite3.connect('deskie_lie.db')
c = conn.cursor()

print('=== Business Email/Phone in DB ===')
c.execute('SELECT name, email, phone FROM businesses LIMIT 15')
for row in c.fetchall():
    print(f"  {row[0][:40]:<40} | email={row[1]} | phone={row[2]}")

print()
print('=== Website Agent - emails/phones extracted ===')
c.execute("""
    SELECT b.name, r.result_json 
    FROM businesses b 
    JOIN research_results r ON b.id = r.business_id 
    WHERE r.agent_name = 'website_agent'
    LIMIT 10
""")
for row in c.fetchall():
    d = json.loads(row[1])
    print(f"  {row[0][:40]:<40} | emails={d.get('emails')} | phones={d.get('phone_numbers')}")

conn.close()
