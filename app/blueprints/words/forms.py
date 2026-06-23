from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField
from wtforms.validators import DataRequired, Length


LANG_CHOICES = [
    ("fr", "法语"), ("en", "英语"), ("ja", "日语"),
    ("de", "德语"), ("es", "西语"), ("ru", "俄语"),
]


class NewListForm(FlaskForm):
    name = StringField("词表名", validators=[DataRequired(), Length(max=200)])
    language_code = SelectField("语言", choices=LANG_CHOICES, validators=[DataRequired()])


class AddWordForm(FlaskForm):
    word = StringField("词", validators=[DataRequired(), Length(max=200)])
    part_of_speech = StringField("词性")
    meaning = TextAreaField("释义")
    example = TextAreaField("例句")
    note = TextAreaField("备注")
