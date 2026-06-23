from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField
from wtforms.validators import DataRequired


class LoginForm(FlaskForm):
    # 不用 Email() 校验器（避免引入 email_validator 依赖）；格式不严格不影响登录。
    email = StringField("邮箱", validators=[DataRequired()])
    password = PasswordField("密码", validators=[DataRequired()])
