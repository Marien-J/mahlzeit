"""The service layer: transactions, permissions and change records. The only layer that writes.

Every public function takes the database session first and, when a person is acting, an Actor.
Write functions commit before they return.
"""
