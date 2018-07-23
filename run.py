import time, json, random
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from websocket import create_connection
import binascii, dataset
import phonenumbers

# Importing settings file
import settings


from modules import nano

db = dataset.connect('sqlite:///users.db')
user_table = db['user']

app = Flask(__name__)

@app.route("/sms", methods=['GET', 'POST'])
def sms_ahoy_reply():

    print(request.values)
    from_number = request.values.get('From')
    from_country = request.values.get('FromCountry')

    user_details = user_table.find_one(number=from_number)
    print(user_details)

    if user_details == None:
        authcode = (random.SystemRandom().randint(1000,9999))
        user_table.insert(dict(number=from_number, time=int(time.time()), count=1, authcode=authcode, claim_last=0))
        user_details = user_table.find_one(number=from_number)    
    else:
        user_table.update(dict(number=from_number, time=int(time.time()), count=(int(user_details['count']) + 1)), ['number'])

    text_body = request.values.get('Body')
    text_body = text_body.lower()

    new_authcode = (random.SystemRandom().randint(1000,9999))

    if 'register' in text_body:
        print('Found register')
        
        account = nano.get_address(user_details['id'])
        # Start our response
        resp = MessagingResponse()

        # Add a message
        resp.message("Welcome to NanoSMS, your address:\n" +  account + ", Code: " + str(new_authcode))

    elif 'details' in text_body:
        print('Found help')
        resp = MessagingResponse()
        resp.message("balance - get your balance\n send - send Nano\n address - your nano address" + ", Code: " + str(new_authcode))

    elif 'address' in text_body:
        print('Found address')
        account = nano.get_address(user_details['id'])
        resp = MessagingResponse()
        resp.message(account  + ", Code: " + str(new_authcode))

    elif 'history' in text_body:
        print('Found address')
        account = nano.get_address(user_details['id'])
        resp = MessagingResponse()
        resp.message("https://www.nanode.co/account/" + account + ", Code: " + str(new_authcode))

    elif 'balance' in text_body:
        print('Found balance')

        account = nano.get_address(user_details['id'])
        print(account)
        previous = nano.get_previous(str(account))
        print(previous)
        print(len(previous))

        pending = nano.get_pending(str(account))
        if (len(previous) == 0) and (len(pending) > 0):
            print("Opening Account")
            nano.open_xrb(int(user_details['id']), account)

        print("Rx Pending: ", pending)
        pending = nano.get_pending(str(account))
        print("Pending Len:" + str(len(pending)))

        while len(pending) > 0:
            pending = nano.get_pending(str(account))
            print(len(pending))
            nano.receive_xrb(int(user_details['id']), account)

        if len(previous) == 0:
            balance = "Empty"
        else:
            previous = nano.get_previous(str(account))
            balance = int(nano.get_balance(previous)) / 1000000000000000000000000

        print(balance)
        # Start our response
        resp = MessagingResponse()

        # Add a message
        resp.message("Balance: " + str(balance) + " nanos" + ", Code: " + str(new_authcode))

    elif 'send' in text_body:
        print('Found send')
        account = nano.get_address(user_details['id'])
        components = text_body.split(" ")

        # Check amount is real
        try:
            amount = int(components[1]) * 1000000000000000000000000
        except:
            resp = MessagingResponse()
            resp.message("Error: Incorrect Amount")
            return str(resp)

        destination = components[2]
        destination = destination.replace("\u202d", "")
        destination = destination.replace("\u202c", "")
        authcode = int(components[3])
        if authcode == int(user_details['authcode']):
            if destination[0] == "x":
                print("xrb addresses")
                nano.send_xrb(destination, amount, account, user_details['id'])
                resp = MessagingResponse()
                resp.message("Sent!" + ", Code: " + str(new_authcode))
                return str(resp)

            else:
                try:
                    phonenum = phonenumbers.parse(destination, from_country)
                    dest_address = phonenumbers.format_number(phonenum, phonenumbers.PhoneNumberFormat.E164)
                except phonenumbers.phonenumberutil.NumberParseException:
                    print("Error")
                    resp = MessagingResponse()
                    resp.message("Error: Incorrect destination address/number")
                    return str(resp)

            if not phonenumbers.is_possible_number(phonenum):
                resp = MessagingResponse()
                resp.message("Error: Incorrect destination")
                return str(resp)

            dest_user_details = user_table.find_one(number=dest_address)
            print(dest_user_details)

            if dest_user_details == None:
                user_table.insert(dict(number=dest_address, time=0, count=0, authcode=0, claim_last=0))
                dest_user_details = user_table.find_one(number=dest_address)

            nano.send_xrb(nano.get_address(dest_user_details['id']), amount, account, user_details['id'])

            resp = MessagingResponse()
            resp.message("Sent!" + ", Code: " + str(new_authcode))

        else:
            resp = MessagingResponse()
            resp.message("Error: Incorrect Auth Code")
            return str(resp)

    elif 'claim' in text_body:
        print("Found claim")
        account = nano.get_address(user_details['id'])
        current_time = int(time.time())
        if current_time > (int(user_details['claim_last']) + 86400):
            print("They can claim")
            amount = 10000000000000000000000000
            nano.send_xrb(account, amount, nano.get_address(10), 10)
            user_table.update(dict(number=from_number, claim_last=int(time.time())), ['number'])

            resp = MessagingResponse()
            resp.message("Claim Success (10 nanos)\nAD1: check out localnanos to exchange nano/VEF\nAD2: Cerveza Polar 6 for 1Nano at JeffMart, 424 Caracas\n" + "Code: " + str(new_authcode))
        else:
            resp = MessagingResponse()
            resp.message("Error: Claim too soon")
            return str(resp)

    elif 'trust' in text_body:
        # Only works with local numbers. Do not supply country code.
        print("Found trust")
        components = text_body.split(" ")

        authcode = int(components[2])
        if authcode == int(user_details['authcode']):
            if "x" in components[1][0]:
                try:
                    if nano.xrb_account(components[1]):
                        xrb_trust = components[1]
                        resp = MessagingResponse()
                        resp.message("Trust address set to " + components[1] + " Code:" +  str(new_authcode))
                        user_table.update(dict(trust_address=xrb_trust, trust_number=0), ['id'])
                    else:
                        print("Invalid address")
                        resp = MessagingResponse()
                        resp.message("Invalid address" + str(new_authcode))
                except KeyError:
                    print("Invalid address")
                    resp = MessagingResponse()
                    resp.message("Invalid address" + str(new_authcode))
            elif components[1].isdigit():
                trust_number = components[1]
                resp = MessagingResponse()
                resp.message("Trust address set to " + components[1] + " Code: " + str(new_authcode))
                user_table.update(dict(trust_address="", trust_number=trust_number), ['id'])
            else:
                print("No valid trust")
                resp = MessagingResponse()
                resp.message("No valid trust" + str(new_authcode))
        else:
            resp = MessagingResponse()
            resp.message("Error: Incorrect Auth Code")
            return str(resp)


    else:
        print('Error')

        # Start our response
        resp = MessagingResponse()

        # Add a message
        resp.message("Error")

    user_table.update(dict(number=from_number, authcode=new_authcode), ['number'])

    return str(resp)

if __name__ == "__main__":
        #Check faucet address on boot to make sure we are up to date
        account = nano.get_address(10)
        print(account)
        previous = nano.get_previous(str(account))
        print(previous)
        print(len(previous))

        pending = nano.get_pending(str(account))
        if (len(previous) == 0) and (len(pending) > 0):
            print("Opening Account")
            nano.open_xrb(int(10), account)

        print("Rx Pending: ", pending)
        pending = nano.get_pending(str(account))
        print("Pending Len:" + str(len(pending)))

        while len(pending) > 0:
            pending = nano.get_pending(str(account))
            print(len(pending))
            nano.receive_xrb(int(10), account)

        app.run(debug=True, host="0.0.0.0", port=5002)
