"""Fail-closed permission policy for company actions."""
from enum import StrEnum
class Action(StrEnum):
 READ="read"; RESEARCH="research"; CREATE_DRAFT="create_draft"; MODIFY_INTERNAL="modify_internal"; CONTACT_CUSTOMER="contact_customer"
 PUBLISH="publish"; SPEND="spend"; CUSTOMER_COMMITMENT="customer_commitment"; REFUND="refund"; PROD_CHANGE="production_change"
OWNER_APPROVAL_REQUIRED={Action.PUBLISH,Action.SPEND,Action.CUSTOMER_COMMITMENT,Action.REFUND,Action.PROD_CHANGE,Action.CONTACT_CUSTOMER}
def permission_decision(action:Action, owner_approved:bool=False)->str:
 if action in OWNER_APPROVAL_REQUIRED and not owner_approved:return "approval_required"
 return "allowed"
