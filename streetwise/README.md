# Streetwise

Players look around a Google Street View panorama somewhere in South
Africa and guess which party won that voting district in the 2024
election, and with what share of the vote. The result also shows which
party won the most seats on the municipality's council in the 2021
municipal election.

## The data

The results are the IEC's **national ballot** results for the 2024
National and Provincial Elections, by voting district. The national ballot
gives the headline result (ANC 40.2%, DA 21.8%, MK 14.6%), and every
voter got one, which is not true of the regional and provincial ballots.

The file comes from the IEC's results site: Downloads, NPE Results, 2024
National Election, National, Downloadable report data. At the time of
writing that is

    https://results.elections.org.za/home/NPEPublicReports/1334/National%20Ballot/Downloadable%20Results/National.zip

Import it, zipped or not:

    ./manage.py import_iec_results National.zip

It takes a few seconds and can be run again safely; districts already
there are updated. The Out of Country district and the two districts that
recorded no votes are skipped. A share of the vote is a party's votes over
all valid votes, as the IEC reports it; turnout counts spoilt votes too.

Then each municipal council's seats, from the IEC's Seat Calculation
Detail report for each municipality (Downloads, ME Results, Local
Government Election 2021). The command fetches the report for every
municipality that has voting districts, so it comes second:

    ./manage.py import_iec_councils

It takes about half a minute and can be run again safely. A party's
seats there are its ward and PR seats together, and a council's total
includes any independent ward councillors. Districts find their council by
the municipality's code ("WC024"), since a few municipalities have been
renamed since 2021.

The largest party on a council isn't necessarily the one running it: 70
councils had no majority in 2021, and coalitions have changed hands since.
The result says only which party is largest, and whether it has a majority.
Four councils (Nelson Mandela Bay among them) were tied for the most seats;
the result names both parties.

The 2026 local elections are on 4 November 2026. Once the IEC has the
seat reports up, `./manage.py import_iec_councils --year 2026` brings them
in, and every puzzle, old ones included, then shows the newer council.

## Making a puzzle

In the Django admin, under Streetwise:

1. Find a street in the district in Google Maps, drop into Street View,
   and turn to face the way players should start out looking.
2. Add a Streetwise puzzle. Pick the voting district (search by its number,
   voting station or municipality) and paste the whole Google Maps address
   into "Street view link". Saving fills in the panorama id and the view.
3. Check the preview, which is cropped exactly as players will see it,
   and the result below it.
4. If the panorama gives the place away (a street sign, a famous
   landmark), tick Rejected. Otherwise set a publish time.

A puzzle can't be published while rejected, and a district whose vote was
a tie for first place can't be used at all. Staff can play any puzzle,
published or not, from the "Open it as a player" link.

For a puzzle made by hand, nothing checks that the panorama is inside the
district; that's up to the editor. Puzzles from `find_panoramas` are
checked against the district boundary.

## Making puzzles in bulk

`find_panoramas` picks voting districts with a mix of winners (flattened,
so it isn't two in three ANC), finds a Google panorama in each and writes
them to a CSV:

    ./manage.py find_panoramas vd2024.shp streetwise-puzzles.csv --count 340

It needs the IEC's 2024 voting-district boundaries as a shapefile (with its
.dbf beside it); a copy is in
https://github.com/j-norwood-young/SA-Maps under "Voting Districts". A
panorama is only kept if Google took it (not a user's photo sphere), it's
from 2015 or later, and it stands inside its district at least 40 m from
the boundary. It uses the Street View Static API's metadata lookups,
which are free; enable that API for the key, or set a separate
`GOOGLE_STREETVIEW_KEY`, since a key restricted to the site's referrers
won't work from a server. Districts that already have a puzzle are left
out, so it can be run again for more.

Then import the CSV, either unpublished or one a day from a date:

    ./manage.py import_streetwise streetwise-puzzles.csv
    ./manage.py import_streetwise streetwise-puzzles.csv --schedule-from 2026-11-01

Importing the same file twice adds nothing new. Keep these CSVs out of
the repository: they say where every future puzzle is.

Editors should still look at each one in the admin before it goes out, and
reject any whose view gives the place away.

## Google Maps

The panorama is shown with the Maps Embed API's Street View mode, which
is free. Put the key in `local_settings.py`:

    GOOGLE_MAPS_EMBED_KEY = "..."

In the Google Cloud console, restrict the key to the Maps Embed API and to
the site's own addresses (HTTP referrers). An Embed key is always visible
in the page, so those restrictions are what protect it.

The embed pins an address card to the panorama's top-left corner. The
page crops it off by drawing the iframe taller than its box and pulling it
up (`--sw-crop` in `streetwise.css`). Nothing is laid over the iframe, and
Google's logo, copyright and terms along the bottom stay in view. Full
screen is turned off, since it would bring the card back.

The panorama starts loading with the page, while the player reads the
rules: the game sits under the splash, laid out but transparent and inert,
because Street View won't fetch its imagery for a frame that's hidden
(`display: none` or `visibility: hidden`). On a decent connection it's
ready by the time they tap Start. Until Google's page has loaded, a
loading screen covers the box. The embed is about 700 KB, mostly Google's
scripts, and is fetched even if the player never starts.

The page carries the panorama id, not the coordinates, but anyone
determined can still look an id up. The result itself only reaches the
browser once the game is over.

## Playing

Five guesses. A guess is right with the right party and a share within
five percentage points (`ATTEMPTS` and `TOLERANCE` in `views.py`). Each
miss reveals the next clue: province, municipality, voting station, then
the runner-up. Guesses live in the player's session, so a refresh doesn't
give them a fresh set, and no login is needed.

When it's over, the result shows how the area voted: the district's 2024
result and the council's largest party in 2021, then each one in full.

The parties' colours are in `streetwise.css`, by the class Django's
`slugify` gives each name (`.sw-p-vf-plus`). Any party not listed there is
grey.
