"""
Remove any API keys that are past their expiration date.
"""
import math

from aurweb import db, time
from aurweb.models.api_key import ApiKey


def main():
    api_keys = db.query(ApiKey).filter(ApiKey.ExpireTS.is_not(None))

    with db.begin():
        for key in api_keys:
            current_time = math.floor(time.now(key.User.Timezone).timestamp())

            if current_time > key.ExpireTS:
                db.delete(key)


if __name__ == "__main__":
    main()
