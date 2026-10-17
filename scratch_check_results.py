import sqlite3
conn = sqlite3.connect('data/tablo_cache.db')
c = conn.cursor()

print('=== SEASON / SERIES PREMIERES ===')
c.execute('''
    SELECT DISTINCT g.title, ga.season_number, ga.episode_number, ga.episode_title, ga.air_datetime, ga.channel_network
    FROM guide_airings ga
    JOIN guide_shows g ON g.path = ga.series_path
    WHERE ga.is_premiere = 1
    ORDER BY ga.air_datetime ASC
''')
for r in c.fetchall():
    print(f'  {r[0]} (S{r[1]} E{r[2]}) - "{r[3]}" on {r[5]} at {r[4]}')

print('\n=== PRIMETIME NEW EPISODES (First 15) ===')
c.execute('''
    SELECT DISTINCT g.title, ga.season_number, ga.episode_number, ga.episode_title, ga.air_datetime, ga.channel_network
    FROM guide_airings ga
    JOIN guide_shows g ON g.path = ga.series_path
    WHERE ga.is_new = 1 AND ga.is_primetime = 1
    ORDER BY ga.air_datetime ASC
    LIMIT 15
''')
for r in c.fetchall():
    print(f'  {r[0]} (S{r[1]} E{r[2]}) - "{r[3]}" on {r[5]} at {r[4]}')
