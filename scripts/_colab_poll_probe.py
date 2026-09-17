from pathlib import Path
import re, requests
local=requests.get('http://127.0.0.1:17493/events/speak/poll?timeout=0',timeout=5)
print('LOCAL_POLL',local.status_code,local.text)
text=Path('/content/drive/MyDrive/voicebox-logs/cloudflared.log').read_text(errors='ignore')
urls=re.findall(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com',text)
url=urls[-1]
print('TUNNEL_URL',url)
remote=requests.get(url+'/events/speak/poll?timeout=0',timeout=20)
print('REMOTE_POLL',remote.status_code,remote.text)
