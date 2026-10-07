# German and Dutch are drafts until reviewed (see docs/decisions.md).

MESSAGES: dict[str, dict[str, str]] = {
    "de": {
        "email.password_reset.subject": "Mahlzeit: Passwort zurücksetzen",
        "email.password_reset.body": (
            "Hallo {name},\n\n"
            "jemand hat ein neues Passwort für dein Mahlzeit-Konto angefordert. "
            "Über diesen Link kannst du es in den nächsten {minutes} Minuten festlegen:\n\n"
            "{link}\n\n"
            "Wenn du das nicht warst, ignoriere diese E-Mail einfach."
        ),
        "push.test.title": "Mahlzeit",
        "push.test.body": "Benachrichtigungen funktionieren auf diesem Gerät.",
        "push.offer.title": "{name} bietet dir eine Mahlzeit an",
        "push.offer.body": "{meal}",
        "push.counter.title": "{name} schlägt etwas anderes vor",
        "push.counter.body": "{meal}",
    },
    "en": {
        "email.password_reset.subject": "Mahlzeit: reset your password",
        "email.password_reset.body": (
            "Hello {name},\n\n"
            "someone asked for a new password for your Mahlzeit account. "
            "Use this link within the next {minutes} minutes to set it:\n\n"
            "{link}\n\n"
            "If this wasn't you, just ignore this email."
        ),
        "push.test.title": "Mahlzeit",
        "push.test.body": "Notifications work on this device.",
        "push.offer.title": "{name} offers you a meal",
        "push.offer.body": "{meal}",
        "push.counter.title": "{name} suggests something else",
        "push.counter.body": "{meal}",
    },
    "nl": {
        "email.password_reset.subject": "Mahlzeit: wachtwoord opnieuw instellen",
        "email.password_reset.body": (
            "Hallo {name},\n\n"
            "iemand heeft een nieuw wachtwoord aangevraagd voor je Mahlzeit-account. "
            "Met deze link kun je het de komende {minutes} minuten instellen:\n\n"
            "{link}\n\n"
            "Was jij dit niet? Dan kun je deze e-mail negeren."
        ),
        "push.test.title": "Mahlzeit",
        "push.test.body": "Meldingen werken op dit apparaat.",
        "push.offer.title": "{name} stelt je een maaltijd voor",
        "push.offer.body": "{meal}",
        "push.counter.title": "{name} stelt iets anders voor",
        "push.counter.body": "{meal}",
    },
}
