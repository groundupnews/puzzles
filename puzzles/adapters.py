from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.utils import filter_users_by_email


class AccountAdapter(DefaultAccountAdapter):
    def save_user(self, request, user, form, commit=True):
        user = super().save_user(request, user, form, commit=False)
        user.username = user.email
        if commit:
            user.save()
        return user

    def send_mail(self, template_prefix, email, context):
        if template_prefix == "account/email/login_code":
            users = filter_users_by_email(email)
            user = users[0] if users else None
            if user is not None:
                context = {
                    **context,
                    "display_name": getattr(getattr(user, "player", None), "display_name", ""),
                    # last_login is only set once a login actually completes,
                    # so it's still None the first time a freshly-created
                    # account (see PasswordlessRequestLoginCodeForm) requests
                    # a code.
                    "is_new_user": user.last_login is None,
                }
        super().send_mail(template_prefix, email, context)
