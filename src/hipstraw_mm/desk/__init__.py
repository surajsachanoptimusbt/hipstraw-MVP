"""The Hipstraw reviewer desk (Nov 6 meeting): requests come in, the agent works them through a fixed pipeline
(ingest, review, position, recommend, workflow), the playbook's rules pick the Lines and Moves, and a human
reviewer approves. Every step is an event on an append-only, hash-chained ledger.
"""
