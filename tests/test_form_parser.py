import unittest

from job_agent.agent.form_parser import parse_fields


class FakeElement:
    def __init__(
        self,
        *,
        tag_name="input",
        attrs=None,
        visible=True,
    ):
        self.tag_name = tag_name
        self.attrs = attrs or {}
        self.visible = visible

    async def evaluate(self, script, *args):
        if "tagName" in script:
            return self.tag_name
        return None

    async def get_attribute(self, name):
        return self.attrs.get(name)

    async def is_visible(self):
        return self.visible

    async def inner_text(self):
        return self.attrs.get("text", "")


class FakeScope:
    def __init__(self, url, elements=None, labels=None):
        self.url = url
        self._elements = elements or []
        self._labels = labels or {}

    async def query_selector_all(self, selector):
        return list(self._elements)

    async def query_selector(self, selector):
        return self._labels.get(selector)


class DetachedScope(FakeScope):
    async def query_selector_all(self, selector):
        raise RuntimeError("Frame was detached")


class FakePage:
    def __init__(self, frames):
        self.frames = frames


class FormParserTests(unittest.IsolatedAsyncioTestCase):
    async def test_parse_fields_scans_all_frames(self):
        label = FakeElement(tag_name="label", attrs={"text": "First Name"})
        input_element = FakeElement(
            attrs={
                "id": "first-name",
                "name": "first_name",
                "type": "text",
            }
        )
        frame = FakeScope(
            "https://jobs.example.com/embed",
            elements=[input_element],
            labels={'label[for="first-name"]': label},
        )
        page = FakePage(frames=[frame])

        fields = await parse_fields(page)

        self.assertEqual(len(fields), 1)
        self.assertEqual(fields[0]["label"], "First Name")
        self.assertEqual(fields[0]["scope_url"], "https://jobs.example.com/embed")

    async def test_parse_fields_skips_hidden_elements(self):
        hidden_element = FakeElement(
            attrs={
                "id": "hidden-email",
                "name": "email",
                "type": "text",
                "aria-label": "Email",
            },
            visible=False,
        )
        frame = FakeScope("https://jobs.example.com/embed", elements=[hidden_element])
        page = FakePage(frames=[frame])

        fields = await parse_fields(page)

        self.assertEqual(fields, [])

    async def test_parse_fields_ignores_detached_frames(self):
        label = FakeElement(tag_name="label", attrs={"text": "First Name"})
        input_element = FakeElement(
            attrs={
                "id": "first-name",
                "name": "first_name",
                "type": "text",
            }
        )
        detached_frame = DetachedScope("https://jobs.example.com/chat")
        valid_frame = FakeScope(
            "https://jobs.example.com/embed",
            elements=[input_element],
            labels={'label[for="first-name"]': label},
        )
        page = FakePage(frames=[detached_frame, valid_frame])

        fields = await parse_fields(page)

        self.assertEqual(len(fields), 1)
        self.assertEqual(fields[0]["label"], "First Name")
