from saathi.actions import Action
from saathi.masking import mask_snapshot, mask_text
from saathi.safety import SafetyLayer, imitates, is_secret_field, looks_like_secret

PAGE = {
    "url": "http://127.0.0.1:8000/index.html",
    "text": "Pay your electricity bill",
    "elements": [
        {"id": 1, "tag": "input", "name": "consumer", "label": "Consumer number"},
        {"id": 2, "tag": "input", "name": "otp", "label": "Enter OTP", "autocomplete": "one-time-code"},
        {"id": 3, "tag": "a", "text": "Pay ₹840", "href": "pay.html"},
        {"id": 4, "tag": "button", "text": "Fetch bill"},
        {"id": 5, "tag": "a", "text": "Claim refund", "href": "http://namma-p0wer.in/refund"},
        {"id": 6, "tag": "input", "type": "password", "name": "pw"},
    ],
}


def layer():
    s = SafetyLayer()
    s.hear("Pay my bill, consumer number 1234567890")
    return s


def test_types_what_the_user_said():
    assert layer().check(Action("type", 1, "1234567890"), PAGE).verdict == "allow"


def test_never_types_what_the_user_did_not_say():
    assert layer().check(Action("type", 1, "9999999999"), PAGE).verdict == "block"


def test_never_types_into_otp_or_password_even_if_user_said_it():
    s = layer()
    s.hear("my otp is 482913")
    assert s.check(Action("type", 2, "482913"), PAGE).verdict == "block"
    assert s.check(Action("type", 6, "482913"), PAGE).verdict == "block"


def test_never_types_aadhaar_or_card_numbers():
    s = layer()
    s.hear("1234 5678 9012 and 4111 1111 1111 1111")
    assert s.check(Action("type", 1, "1234 5678 9012"), PAGE).verdict == "block"
    assert s.check(Action("type", 1, "4111 1111 1111 1111"), PAGE).verdict == "block"


def test_asks_before_paying():
    assert layer().check(Action("click", 3), PAGE).verdict == "confirm"


def test_plain_click_is_allowed():
    assert layer().check(Action("click", 4), PAGE).verdict == "allow"


def test_blocks_lookalike_link_and_navigation():
    d = layer().check(Action("click", 5), PAGE)
    assert d.verdict == "block" and "imitates" in d.reason
    assert layer().check(Action("navigate", url="http://namma-p0wer.in/x"), PAGE).verdict == "block"


def test_blocks_unknown_site_and_allows_same_site():
    assert layer().check(Action("navigate", url="https://example.org"), PAGE).verdict == "block"
    assert layer().check(Action("navigate", url="help.html"), PAGE).verdict == "allow"


def test_scam_page_needs_confirmation():
    page = dict(PAGE, text="URGENT: your connection will be blocked in 2 hours. Update KYC now.")
    assert layer().check(Action("click", 4), page).verdict == "confirm"


def test_unknown_element_is_blocked():
    assert layer().check(Action("click", 99), PAGE).verdict == "block"


def test_layer_off_allows_everything():
    s = SafetyLayer(enabled=False)
    assert s.check(Action("type", 2, "482913"), PAGE).verdict == "allow"


def test_helpers():
    assert is_secret_field({"label": "Aadhaar number"})
    assert not is_secret_field({"label": "Consumer number"})
    assert looks_like_secret("4111-1111-1111-1111")
    assert not looks_like_secret("1234567890")
    assert imitates("namma-p0wer.in", {"nammapower.in"}) == "nammapower.in"
    assert imitates("nammapower.in", {"nammapower.in"}) is None


def test_masking_hides_secrets_before_they_leave():
    assert "[aadhaar hidden]" in mask_text("Aadhaar 1234 5678 9012")
    assert mask_text("card 4111 1111 1111 1111") == "card [card hidden]"
    assert "[aadhaar hidden]" in mask_text("id 1234-5678-9012.")
    assert mask_text("consumer 1234567890") == "consumer 1234567890"
    assert "482913" not in mask_text("Your OTP is 482913")
    snap = {"text": "", "elements": [{"id": 1, "type": "password", "value": "hunter2"},
                                     {"id": 2, "name": "consumer", "value": "1234567890"}]}
    masked = mask_snapshot(snap)
    assert masked["elements"][0]["value"] == "[hidden]"
    assert masked["elements"][1]["value"] == "1234567890"
    assert snap["elements"][0]["value"] == "hunter2"  # original untouched


def test_types_words_the_user_said_in_any_order():
    s = SafetyLayer()
    s.hear("Open flipkart and add 1 kg atta to the cart")
    search = {"url": "https://www.flipkart.com/", "text": "", "elements": [{"id": 1, "tag": "input", "name": "q", "label": "Search"}]}
    assert s.check(Action("type", 1, "atta 1kg"), search).verdict == "allow"
    assert s.check(Action("type", 1, "482913"), search).verdict == "block"  # a number from a page, never said
    assert s.check(Action("type", 1, "atta sugar"), search).verdict == "block"  # one word not said


def test_kannada_words_count_as_said():
    s = SafetyLayer()
    s.hear("ಬಿಲ್ ಪಾವತಿಸು 1234567890")
    assert s.check(Action("type", 1, "1234567890"), PAGE).verdict == "allow"


def test_opens_a_site_the_user_named_but_not_lookalikes():
    s = SafetyLayer(allowed_hosts={"127.0.0.1"})
    s.hear("Open flipkart and add 1 kg atta to the cart")
    assert s.check(Action("navigate", url="https://www.flipkart.com/"), PAGE).verdict == "allow"
    for bad in ("https://flipkart-offers.shop/", "https://flipkart.scam.in/", "https://f1ipkart.com/", "https://example.org/"):
        assert s.check(Action("navigate", url=bad), PAGE).verdict == "block", bad


def test_add_to_cart_is_allowed_but_buying_asks_first():
    s = SafetyLayer(allowed_hosts={"www.flipkart.com"})
    s.hear("add 1 kg atta to the cart")
    shop = {"url": "https://www.flipkart.com/p", "text": "", "elements": [
        {"id": 1, "tag": "button", "text": "Add to cart"}, {"id": 2, "tag": "button", "text": "Buy now"},
        {"id": 3, "tag": "button", "text": "Place order"}]}
    assert s.check(Action("click", 1), shop).verdict == "allow"
    assert s.check(Action("click", 2), shop).verdict == "confirm"
    assert s.check(Action("click", 3), shop).verdict == "confirm"
