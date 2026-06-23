"""管理 CLI：建账号 / 重置密码 / 停用 / 重置额度。

全部走 provisioning 的 BYPASSRLS 连接，不依赖请求上下文。
"""
import click

from app.services import provisioning


def register_commands(app):

    @app.cli.command("create-user")
    @click.option("--email", required=True)
    @click.option("--name", required=True)
    @click.option("--admin", is_flag=True, default=False)
    @click.option("--tz", default="Asia/Shanghai", help="用户时区，默认 Asia/Shanghai")
    def create_user(email, name, admin, tz):
        """建账号（一事务建 User + UserSettings + UserQuota）。"""
        try:
            uid, pw = provisioning.create_user_with_defaults(
                email, name, admin=admin, timezone=tz
            )
        except provisioning.UserExistsError:
            raise click.ClickException(f"邮箱已存在：{email}")
        click.echo(f"用户已创建：{email} (id={uid})  初始密码：{pw}")

    @app.cli.command("reset-password")
    @click.option("--email", required=True)
    def reset_password(email):
        """重置密码，打印新密码。"""
        try:
            pw = provisioning.reset_password(email)
        except provisioning.UserNotFoundError:
            raise click.ClickException(f"用户不存在：{email}")
        click.echo(f"已重置：{email}  新密码：{pw}")

    @app.cli.command("deactivate-user")
    @click.option("--email", required=True)
    def deactivate_user(email):
        """停用账号（is_active=False）。"""
        try:
            provisioning.deactivate_user(email)
        except provisioning.UserNotFoundError:
            raise click.ClickException(f"用户不存在：{email}")
        click.echo(f"已停用：{email}")

    @app.cli.command("reset-quota")
    @click.option("--email", required=True)
    def reset_quota(email):
        """清零今日 token 额度。"""
        try:
            provisioning.reset_quota(email)
        except provisioning.UserNotFoundError:
            raise click.ClickException(f"用户不存在：{email}")
        click.echo(f"已重置额度：{email}")
