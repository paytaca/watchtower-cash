class MessageComponent(dict):
    pass

# ----------- #

class Text(MessageComponent):
    TYPE = "text"

    def __init__(self, text, **kwargs):
        assert isinstance(text, (str, dict))
        return super().__init__(text=text, type=self.TYPE, **kwargs)

class PlainText(Text):
    TYPE = "plain_text"

class Markdown(Text):
    TYPE = "mrkdwn"

class Button(Text):
    TYPE = "button"

class Divider(MessageComponent):
    TYPE = "divider"

    def __init__(self, *args, **kwargs):
        return super().__init__(type=self.TYPE, *args, **kwargs)
    
class Emoji(MessageComponent):
    def __init__(self, name, **kwargs):
        assert isinstance(name, str)
        return super().__init__(name=name, type="emoji", **kwargs)
    
class Header(MessageComponent):
    TYPE = "header"

    def __init__(self, text, **kwargs):
        assert isinstance(text, dict)
        return super().__init__(text=text, type=self.TYPE, **kwargs)

# ----------- #

class ListTypeBlock(MessageComponent):
    LIST_PROPERTY = ""
    TYPE = None

    def __init__(self, *args, **kwargs):
        if self.TYPE is not None: kwargs["type"] = self.TYPE
        if len(args) and not self.LIST_PROPERTY in kwargs:
            kwargs[self.LIST_PROPERTY] = args
        return super().__init__(**kwargs)

class Blocks(ListTypeBlock):
    LIST_PROPERTY = "blocks"
    TYPE = None

class SectionBlock(ListTypeBlock):
    LIST_PROPERTY = "fields"
    TYPE = "section"

class ContextBlock(ListTypeBlock):
    LIST_PROPERTY = "elements"
    TYPE = "context"

class RichText(ListTypeBlock):
    LIST_PROPERTY = "elements"
    TYPE = "rich_text"

class RichTextList(ListTypeBlock):
    LIST_PROPERTY = "elements"
    TYPE = "rich_text_list"

class RichTextSection(ListTypeBlock):
    LIST_PROPERTY = "elements"
    TYPE = "rich_text_section"
