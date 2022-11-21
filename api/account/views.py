from ninja import NinjaAPI
import random
import hashlib
import string
import logging
from eth_account.messages import defunct_hash_message
from web3.auto import w3
from ninja_jwt.controller import NinjaJWTDefaultController
from ninja_extra import NinjaExtraAPI
from ninja import Schema
from .models import Account

log = logging.getLogger(__name__)

api = NinjaExtraAPI()
api.register_controllers(NinjaJWTDefaultController)


class ChallengeSubmission(Schema):
    address: str
    signature: str


CHALLENGE_STATEMENT = "I authorize the passport scorer.\n\nnonce:"

def get_random_username():
    return "".join(random.choice(string.ascii_letters) for i in range(32))


@api.get("/challenge")
def challenge(request, address: str):
    challenge = {
        "statement": CHALLENGE_STATEMENT,
        "nonce": hashlib.sha256(
            str(
                address
                # + "".join(random.choice(string.ascii_letters) for i in range(32))  TODO: need to track the 'random' part
            ).encode("utf")
        ).hexdigest(),
    }
    return challenge


from ninja_jwt.schema import TokenObtainPairSerializer
from ninja_jwt.controller import TokenObtainPairController
from ninja_jwt.exceptions import AuthenticationFailed
from ninja_extra import api_controller, route
from ninja_schema import Schema


class TokenObtainPairOutSchema(Schema):
    refresh: str
    access: str
    # user: UserSchema


class UserSchema(Schema):
    first_name: str
    email: str


class MyTokenObtainPairOutSchema(Schema):
    refresh: str
    access: str
    user: UserSchema


from pydantic import root_validator
from typing import Dict, Optional, Type, cast

from django.contrib.auth import get_user_model

class MyTokenObtainPairSchema(TokenObtainPairSerializer):
    @root_validator(pre=True)
    def validate_inputs(cls, values: Dict) -> dict:
        log.debug("validate_inputs %s", values)
        # return super().validate_inputs(values)
        log.debug("payload: %s", values)

        address = values.get("address")
        signature = values.get("signature")

        challenge_string = CHALLENGE_STATEMENT
        # check for valid sig
        message_hash = defunct_hash_message(text=challenge_string)
        signer = w3.eth.account.recoverHash(message_hash, signature=signature)

        log.debug("signer:  %s", signer)
        address_lower = address.lower()
        sig_is_valid = address_lower == signer.lower()

        # TODO: return JWT token to the user
        if not sig_is_valid:
            raise AuthenticationFailed(
                cls._default_error_messages["no_active_account"]
            )

        try:
            account = Account.objects.get(address=address_lower)
        except Account.DoesNotExist:
            log.debug("Create user")
            user = get_user_model().objects.create_user(username=get_random_username())
            log.debug("Create user %s", user)
            user.save()
            log.debug("Create user %s", user)
            account = Account(address=address_lower, user=user)
            log.debug("Create account %s", account)
            account.save()
            log.debug("Create account %s", account)

        cls._user = account.user
        log.debug("Create cls._user %s", cls._user)
        return values

    def output_schema(self):
        log.debug("output_schema")
        out_dict = self.dict(exclude={"password"})
        log.debug("output_schema %s", out_dict)
        out_dict.update(user=UserSchema.from_orm(self._user))
        log.debug("output_schema %s", out_dict)
        ret = MyTokenObtainPairOutSchema(**out_dict)
        log.debug("output_schema ret %s", ret)
        return MyTokenObtainPairOutSchema(**out_dict)


@api.post("/test", response=MyTokenObtainPairOutSchema)
def obtain_token(self, user_token: MyTokenObtainPairSchema):
    log.debug("====> test user_token %s", user_token)
    ret = user_token.output_schema()
    log.debug("====> test ret %s", ret)
    return ret


@api.post("/submit_signed_challenge", response=TokenObtainPairOutSchema)
def submit_siigned_challenge(request, payload: ChallengeSubmission):
    log.debug("payload: %s", payload)

    address = payload.address
    signature = payload.signature

    challenge_string = CHALLENGE_STATEMENT
    # check for valid sig
    message_hash = defunct_hash_message(text=challenge_string)
    signer = w3.eth.account.recoverHash(message_hash, signature=signature)

    log.debug("signer:  %s", signer)
    sig_is_valid = address.lower() == signer.lower()

    # TODO: return JWT token to the user
    return {"ok": sig_is_valid}