"""Sales channel registry; capability discovery does not imply connected access."""
from dataclasses import dataclass
@dataclass(frozen=True)
class ChannelDefinition:
 key:str
 label:str
 seller_region_check_required:bool=True
 payment_withdrawal_check_required:bool=True
 external_publish_approval_required:bool=True
@dataclass(frozen=True)
class ChannelStatus:
 channel_key:str
 discovered:bool=False
 eligibility_verified:bool=False
 account_connected:bool=False
 credentials_present:bool=False
 test_passed:bool=False
 publishing_enabled:bool=False
 def ready_for_listing_draft(self):return self.discovered
 def ready_for_publish(self):return all((self.eligibility_verified,self.account_connected,self.credentials_present,self.test_passed,self.publishing_enabled))
 def explain_blockers(self):
  checks={"seller eligibility":self.eligibility_verified,"account connection":self.account_connected,"credentials":self.credentials_present,"connection test":self.test_passed,"publishing permission":self.publishing_enabled}
  return [name for name,ok in checks.items() if not ok]
CHANNELS=(ChannelDefinition("etsy","Etsy"),ChannelDefinition("gumroad","Gumroad"),ChannelDefinition("itch","itch.io"),ChannelDefinition("own_store","Owned storefront"))
