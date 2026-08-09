from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField
from wtforms.validators import DataRequired, ValidationError

from app.i18n import translate as _


class LoginForm(FlaskForm):
    # 不用 Email() 校验器（避免引入 email_validator 依赖）；格式不严格不影响登录。
    email = StringField("邮箱", validators=[DataRequired()])
    password = PasswordField("密码", validators=[DataRequired()])


class RegisterForm(FlaskForm):
    email = StringField("邮箱", validators=[DataRequired()])

    def validate_email(self, field):
        value = (field.data or "").strip()
        local, separator, domain = value.rpartition("@")
        if (
            not separator
            or not local
            or not domain
            or "@" in local
            or "." not in domain
            or len(value) > 254
        ):
            raise ValidationError(_("auth.registration.invalid_email"))
        field.data = value


class PasswordSetupForm(FlaskForm):
    password = PasswordField("密码", validators=[DataRequired()])
    confirm_password = PasswordField("确认密码", validators=[DataRequired()])

    def validate_password(self, field):
        if field.data and len(field.data) < 8:
            raise ValidationError(_("auth.password_setup.too_short"))

    def validate_confirm_password(self, field):
        if field.data != self.password.data:
            raise ValidationError(_("auth.password_setup.mismatch"))
