"""Persistent delegation record repository placeholder interface.

The concrete schema is created by the application runtime so that delegation
records share the same SQLite transaction and audit boundary as work items.
"""
class DelegationRepository:
    def __init__(self, connection, lock):
        self.connection=connection
        self.lock=lock
