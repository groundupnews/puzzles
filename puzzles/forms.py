from allauth.account.adapter import get_adapter
from allauth.account.forms import RequestLoginCodeForm
from allauth.account.models import EmailAddress
from allauth.account.utils import filter_users_by_email, setup_user_email
from allauth.core import context, ratelimit


class PasswordlessRequestLoginCodeForm(RequestLoginCodeForm):
    """Requesting a login code for an unknown email creates the account,
    instead of allauth's default of emailing "no account with this address"."""

    def clean_email(self) -> str:
        adapter = get_adapter()
        email = self.cleaned_data["email"]
        users = filter_users_by_email(email, is_active=True, prefer_verified=True)
        if not ratelimit.consume(
            context.request, action="request_login_code", key=email.lower()
        ):
            raise adapter.validation_error("too_many_login_attempts")
        self._user = users[0] if users else self._create_user(email)
        return email

    def _create_user(self, email):
        request = context.request
        adapter = get_adapter()
        user = adapter.new_user(request)
        adapter.save_user(request, user, self, commit=True)
        setup_user_email(request, user, [EmailAddress(email=email)])
        return user
