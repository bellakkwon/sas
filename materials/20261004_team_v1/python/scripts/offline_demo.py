"""Safe synthetic example: normalize and inspect URL strings without requests."""
import csv,json,sys
from pathlib import Path
P=Path(__file__).resolve().parents[1];sys.path.insert(0,str(P/'src'))
from scamlens.preprocessing import normalize_text,extract_urls,defang_url
from scamlens.url_features import lexical_features
for row in csv.DictReader((P.parent/'data/samples/messages.csv').open()):
    text=normalize_text(row['text_raw_masked'])
    print(json.dumps({'id':row['message_id'],'synthetic':True,'text':text,'url_features':[{'url':defang_url(u),'features':lexical_features(u)} for u in extract_urls(row['text_raw_masked'])]},ensure_ascii=False))
print('Synthetic preprocessing example only; no classifier or measured detection performance.')
