"""Public operation projection; excludes inputs and provider evidence."""


def public_operation(value):
    # Inputs, provider credentials and attempt details never become tool logs.
    fields = ("id","kind","status","version","created_at","updated_at","external_job_id","actual_cost")
    return {key:value[key] for key in fields if key in value}
