"""Routes de la trésorerie."""
from django.urls import path

from finance import views

app_name = "finance"

urlpatterns = [
    path("", views.finance_list, name="finance_list"),
    path("livre/", views.finance_ledger, name="ledger"),
    path("ecritures/creer/", views.entry_create, name="entry_create"),
    path("ecritures/<int:pk>/", views.entry_detail, name="entry_detail"),
    path("ecritures/<int:pk>/modifier/", views.entry_edit, name="entry_edit"),
    path("ecritures/<int:pk>/dupliquer/", views.entry_duplicate, name="entry_duplicate"),
    path("ecritures/<int:pk>/supprimer/", views.entry_delete, name="entry_delete"),
    path("comptes/", views.accounts, name="accounts"),
    path("comptes/creer/", views.account_create, name="account_create"),
    path("comptes/<int:pk>/", views.account_edit, name="account_edit"),
    path("coffre/", views.cash, name="cash"),
    path("categories/", views.categories, name="categories"),
    path("import/", views.import_view, name="import"),
    path("import/lancer/", views.import_run, name="import_run"),
    path("import/<int:pk>/annuler/", views.import_revert, name="import_revert"),
    path("export/", views.export, name="export"),
    path("bilan/", views.balance, name="balance"),
    path("clotures/", views.locks, name="locks"),
    path("clotures/creer/", views.lock_create, name="lock_create"),
    path("clotures/<int:pk>/rouvrir/", views.lock_reopen, name="lock_reopen"),
]
