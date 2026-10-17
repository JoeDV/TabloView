import urllib.request
import urllib.parse
import json

base = "http://localhost:7070"

# 1. Shows
shows_data = json.loads(urllib.request.urlopen(f"{base}/api/shows").read().decode("utf-8"))
print("Shows count:", shows_data["count"])
sample_show = shows_data["shows"][0]
print("First Show:", sample_show["title"], f"({sample_show['episode_count']} eps, cover: {sample_show['cover_url']})")

# 2. Episodes
show_id = sample_show["id"]
eps_url = f"{base}/api/shows/episodes?show_id={urllib.parse.quote(show_id)}"
eps_data = json.loads(urllib.request.urlopen(eps_url).read().decode("utf-8"))
print(f"Episodes count for {sample_show['title']}:", eps_data["count"])
sample_ep = eps_data["episodes"][0]
print("First Episode:", sample_ep["title"], f"(ID: {sample_ep['id']}, Status: {sample_ep['status']})")

# 3. Image Proxy
img_url = f"{base}{sample_show['cover_url']}"
img_res = urllib.request.urlopen(img_url)
print("Image Proxy Status:", img_res.status, "Bytes:", len(img_res.read()))

# 4. M3U Playlist
m3u_url = f"{base}/api/episodes/{sample_ep['id']}/playlist.m3u"
m3u_res = urllib.request.urlopen(m3u_url)
print("M3U Status:", m3u_res.status)
print("M3U Content Preview:\n" + m3u_res.read().decode("utf-8").strip())

# 5. Storage
storage = json.loads(urllib.request.urlopen(f"{base}/api/storage").read().decode("utf-8"))
print("Storage:", storage["used_gb"], "GB used /", storage["free_gb"], "GB free (", storage["percent_used"], "% )")
print("\n[ALL TESTS PASSED SUCCESSFULLY!]")
