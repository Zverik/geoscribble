import os

BASE_URL = os.getenv('BASE_URL', '')

# Set to localhost or a socket path.
PG_HOST = os.getenv('PGHOST', '/var/run/postgresql')

# Might want to use a proper user.
PG_USER = os.getenv('PGUSER', 'postgres')

# These are pretty much standard.
PG_PORT = os.getenv('PGPORT', '5432')
PG_DATABASE = os.getenv('PGDATABASE', '')

# Geoscribble-specific numbers
MAX_POINTS = int(os.getenv('MAX_POINTS', '100'))
MAX_LENGTH = int(os.getenv('MAX_LENGTH', '5000'))  # in meters
DEFAULT_AGE = int(os.getenv('DEFAULT_AGE', '91'))  # three months

# For bbox requests
MAX_COORD_SPAN = float(os.getenv('MAX_COORD_SPAN', '0.3'))
MAX_IMAGE_WIDTH = int(os.getenv('MAX_IMAGE_WIDTH', '3000'))
MAX_IMAGE_HEIGHT = int(os.getenv('MAX_IMAGE_HEIGHT', '2000'))

# Fonts for labels
FONT = os.getenv('FONT', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')

# Email for geocoder
EMAIL = os.getenv('EMAIL', 'geoscribble@example.com')
MAX_GEOCODE = int(os.getenv('MAX_GEOCODE', '20'))

# For OpenStreetMap authentication
SECRET_KEY = os.getenv('SECRET_KEY', 'whatever')
OAUTH_ID = os.getenv('OAUTH_ID', '')
OAUTH_SECRET = os.getenv('OAUTH_SECRET', '')

try:
    from .config_local import *
except ImportError:
    pass
