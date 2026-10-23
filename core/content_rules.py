"""Content rules shared by the AI draft, editor, and speech pipeline."""
import re


REQUIRED_OUTRO = "nhấc máy lên và gọi ngay cho số trên màn hình để được tui dẫn đi xem phòng nha."


def prepare_voiceover(text: str) -> str:
    body = re.sub(re.escape(REQUIRED_OUTRO.rstrip(".")) + r"[.!?]*", "", text.strip(), flags=re.IGNORECASE)
    body = body.strip(" \t\r\n.,;:")
    if not body:
        raise ValueError("Hãy nhập lời bình có câu mở đầu thu hút trước khi tạo giọng.")
    punctuation = "" if body.endswith(("!", "?")) else "."
    return f"{body}{punctuation} {REQUIRED_OUTRO}"


def caption_copies_review(caption: str, script: str) -> bool:
    def words(text):
        text = re.sub(r"#[\w]+", "", text)
        return " ".join(re.findall(r"\w+", text.casefold()))
    caption_text, review_text = words(caption), words(script)
    if not caption_text or not review_text:
        return False
    if caption_text == review_text or review_text in caption_text:
        return True
    if len(caption_text.split()) >= 12 and caption_text in review_text:
        return True
    sentences = re.split(r"[.!?\n]+", script)
    return any(len(words(sentence).split()) >= 8 and words(sentence) in caption_text for sentence in sentences)
