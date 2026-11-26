import pytest
from opencompany.product import ProductDraft,ProductStage
from opencompany.channels import ChannelStatus,CHANNELS

def test_product_requires_files_and_quality_checks():
 draft=ProductDraft("Sample pack","Printable learning activity","A pack of printable pages",100,"USD")
 with pytest.raises(ValueError):draft.validate_for_owner_review()
 good=ProductDraft("Sample pack","Printable learning activity","A pack of printable pages",100,"USD",("page.pdf",),("Print check","Content review"),ProductStage.QA)
 assert good.validate_for_owner_review()
def test_channel_not_publish_ready_by_default():
 channel=ChannelStatus(CHANNELS[0].key)
 assert not channel.ready_for_publish()
 assert len(channel.explain_blockers())==5
