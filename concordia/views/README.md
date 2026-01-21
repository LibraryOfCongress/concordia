## **init**.py

Initializes the `views` module and re-exports submodules for chained attribute access
such as `views.campaigns`. Also includes some basic views.

### Class-based Views

-   **HomeView** - A `ListView` displaying featured campaigns on the homepage

### Function-based Views

-   **healthz** - Returns a JSON response with system and application status

## accounts.py

Views related to user account management, including login, registration and profile updates

### Class-based Views

-   **ConcordiaPasswordResetConfirmView** - Customized password reset confirmation
-   **ConcordiaPasswordResetRequestView** - Customized password reset requests
-   **ConcordiaRegistrationView** - Custom registration view with rate limiting
-   **ConcordiaLoginView** - Login view with Turnstile challenge validation
-   **AccountProfileView** - View for managing a user's profile and displaying contributions
-   **AccountDeletionView** - View for users to delete their account (or anonymize it)
-   **EmailReconfirmationView** - Handles confirming a user's changed email address

### Function-based Views

-   **account_letter** - Generates and returns a PDF letter summarizing contributions
-   **get_pages** - Renders a fragment of recent contributed pages

### Functions

-   **registration_rate** - Rate-limit for failed registration attempts

## ajax.py

AJAX endpoints for dynamic client interactions

### Function-based Views

-   **ajax_session_status** - Returns user-specific session data used by the frontend
-   **ajax_messages** - Returns any queued messages for the current user
-   **generate_ocr_transcription** - Generates a new transcription using OCR
-   **rollback_transcription** - Reverts transcription to the previous version
-   **rollforward_transcription** - Reverts the most recent transcription rollback
-   **save_transcription** - Saves a new transcription
-   **submit_transcription** - Marks a transcription as submitted for review
-   **review_transcription** - Accepts or rejects a submitted transcription
-   **submit_tags** - Updates the tag list for an asset
-   **reserve_asset** - Manages reservation of an asset to prevent conflicts

### Functions

-   **get_transcription_superseded** - Determines if the superseded transcription is valid
-   **update_reservation** - Updates the timestamp for a reservation
-   **obtain_reservation** - Creates a new reservation

## assets.py

Views for displaying asset detail pages and redirecting users to the next appropriate asset

### Class-based Views

-   **AssetDetailView** - Displays the transcription interface for a single asset

### Function-based Views

-   **redirect_to_next_asset** - Redirects to provided asset
-   **redirect_to_next_reviewable_asset** - Finds and redirects to a reviewable asset
-   **redirect_to_next_transcribable_asset** - Finds and redirects to a transcribable asset
-   **redirect_to_next_reviewable_campaign_asset** - Finds and redirects to the a reviewable asset for a campaign
-   **redirect_to_next_transcribable_campaign_asset** - Finds and redirects to a transcribable asset for a campaign
-   **redirect_to_next_reviewable_topic_asset** - Finds and redirects to a reviewable asset for a topic
-   **redirect_to_next_transcribable_topic_asset** - Finds and redirects to a transcribable asset for a topic

## campaigns.py

Views for listing campaigns, rendering campaign details, showing reports and filtering by reviewable status

### Class-based Views

-   **CampaignListView** - Lists all active campaigns (unused)
-   **CompletedCampaignListView** - Lists all completed and retired campaigns
-   **CampaignTopicListView** - Primary active campaign list view; also includes active topics
-   **CampaignDetailView** - Shows full details about a single campaign
-   **FilteredCampaignDetailView** - Variant of `CampaignDetailView` that applies filtering based on the user
-   **ReportCampaignView** - Displays a campaign report summarizing stats such as asset counts and contributors

## decorators.py

Custom decorators used by views

### Functions

-   **default_cache_control** - Applies default public caching headers for pages that don't vary per user
-   **user_cache_control** - Applies public caching headers with variation for logged-in users
-   **validate_anonymous_user** - Validates anonymous users via Turnstile before processing requests
-   **reserve_rate** - Returns a rate-limit value for unauthenticated users for reserving assets
-   **next_asset_rate** - Returns a rate-limit value for unauthenicated users for next\_\*\_asset views

## items.py

Views for displaying individual item detail pages

### Class-based Views

-   **ItemDetailView** - Displays a paginated list of assets within an item
-   **FilteredItemDetailView** - Variant of `ItemDetailView` that applies filtering based on the user

## maintenance_mode.py

Views for toggling the site's maintenance mode. Only accessible to superusers

### Function-based Views

-   **maintenance_mode_off** - Disables maintenance mode
-   **maintenance_mode_on** - Enables maintenance mode
-   **maintenance_mode_frontend_available** - Enables access to the frontend for staff while in maintenance mode
-   **maintenance_mode_frontend_unavailable** - Disables access to the frontend for staff while in maintenance mode

## projects.py

Views for displaying project detail pages

### Class-based Views

-   **ProjectDetailView** - Displays a project and its items
-   **FilteredProjectDetailView** - Variant of `ProjectDetailView` that applies filtering based on the user

## rate_limit.py

Custom handler for responding to requests that exceed rate limits

### Function-based Views

-   **ratelimit_view** - Returns a 429 response when a user is rate-limited

## simple_pages.py

Views and redirects for rendering static pages stored in the database

### Function-based Views

-   **simple_page** - Renders a simple static page from the database
-   **about_simple_page** - Renders the "about" simple page, which includes some additional data

### Class-based Views

-   **HelpCenterRedirectView** - Redirects old help center URLs to new equivalents
-   **HelpCenterSpanishRedirectView** - Redirects old Spanish help center URLs to new equivalents

## topics.py

View for displaying a topic's detail page

### Class-based Views

-   **TopicDetailView** - Displays a topic's associated projects

## utils.py

Utility functions, constants and mixins used throughout the views module

### Constants

-   **ASSETS_PER_PAGE** - Default number of assets to show per page
-   **PROJECTS_PER_PAGE** - Default number of projects to show per page
-   **ITEMS_PER_PAGE** - Default number of items to show per page
-   **URL_REGEX** - Regular expression used to detect URLs in transcription text
-   **MESSAGE_LEVEL_NAMES** - Dictionary mapping Django message levels to lowercase names

### Functions

-   **\_get_pages** - Returns a queryset of assets a user has worked on
-   **calculate_asset_stats** - Adds contributor and transcription status to the provided assets
-   **annotate_children_with_progress_stats** - Annotates a list of objects with progress information

### Classes

-   **AnonymousUserValidationCheckMixin** - Requires anonymous users to pass Turnstile validation

## visualization.py

Views for displaying visualizations

### Classes

-   **VisualizationDataView** - Returns JSON representing the visualization `name`
