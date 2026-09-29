"""Verified source comment history -> the four investigation/client columns.

Statuses come from TitleVision, never from guesses about comment wording.
Our comment authors are identified by the vendor's source user list/account IDs.
"""
from datetime import datetime
from urllib.parse import urlparse,parse_qs
import re

FINAL={'Chargeable','Non-Chargeable'}
ACCEPTED={'Accepted','Auto-Accepted'}

def fields(record,required=False):
 values=record['values'];status=values[0];history=record.get('statusHistory')
 if not history:
  if required and status!='New':raise ValueError('Status comment history is missing; collect these dates again')
  return ['','','','']
 if history.get('schema')!=1:raise ValueError('Status comment history schema changed')
 order=parse_qs(urlparse(record['url']).query).get('PublicOrderId',[''])[0]
 url=urlparse(history.get('url',''));query=parse_qs(url.query)
 if url.scheme!='https' or url.netloc!='tv.datatracetitle.com' or url.path!='/UserErrors.aspx' or query.get('EditMode')!=['Status'] or query.get('UserErrorId')!=[record.get('sourceId')] or query.get('PublicOrderId')!=[order] or history.get('sourceId')!=record.get('sourceId') or history.get('orderId')!=order:
  raise ValueError('Status comment history does not match its error identity')
 if history.get('status')!=status or history.get('vendor')!=values[2]:raise ValueError('Status comment history no longer matches the source status/vendor')
 users=history.get('vendorUsers');comments=history.get('comments')
 if not isinstance(users,list) or not users or any(not isinstance(u,str) or not u.strip() for u in users) or not isinstance(comments,list):raise ValueError('Invalid source comment authors or rows')
 own={u.casefold() for u in users};parsed=[]
 for row in comments:
  if not isinstance(row,list) or len(row)!=3 or any(not isinstance(v,str) for v in row):raise ValueError('Invalid status comment row')
  stamp,user,text=row
  try:at=datetime.strptime(stamp,'%m/%d/%Y %I:%M:%S %p')
  except ValueError:raise ValueError('Unrecognized status comment date')
  if not user.strip():raise ValueError('Status comment author is missing')
  # Deleted/reassigned ADS accounts may disappear from the current user list.
  internal=user.casefold() in own or bool(re.search(r'(^ADSSP2_|_ADS(?:SearchType|SP2|P2)$)',user,re.I))
  if text.strip():parsed.append((at,user,text,internal))
 parsed.sort(key=lambda r:r[0])
 def latest(rows):
  if not rows:return None
  last=rows[-1]
  if any(r[0]==last[0] and r[1:3]!=last[1:3] for r in rows):raise ValueError('Conflicting latest status comments; review required')
  return last
 client=latest([r for r in parsed if not r[3]]) if status in FINAL else None
 vendor=[r for r in parsed if r[3]]
 investigation=latest([r for r in vendor if not client or r[0]<=client[0]])
 if vendor and client and not investigation:
  # An external note preceding every vendor reply is not a reply to our dispute.
  client=None;investigation=latest(vendor)
 # The confirmed convention records the vendor challenge as Disputed even after
 # the client resolves it. A final error without a vendor reply has no invented dispute.
 inv=status if status in ACCEPTED|{'Disputed'} else 'Disputed' if status in FINAL and investigation else ''
 return [inv,investigation[2] if inv and investigation else '',status if status in FINAL else '',client[2] if client else '']
