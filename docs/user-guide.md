# User guide

The browser workspace lives at `/ui/projects`. Solar Forge Boards currently uses a dark cyberpunk
theme and is designed around projects containing story cards.

## Projects

Create a project from the Projects page with a unique name and an optional description. Opening a
project shows its five workflow lanes and creates no stories automatically. New projects receive the
four default tags: Business, Coding, Configuration, and Spike.

Open **Customize** on a board to edit its name and description. You can also archive a project
after confirming the action. Archiving preserves every story and activity event but makes the
project read-only; use **Restore project** from the archived board to resume planning. Permanent
project deletion is not available.

## Stories

Select **Forge a story** on a project board. A story supports:

- **Title**: required, up to 200 characters.
- **Description**: optional user, business, or outcome context, up to 10,000 characters.
- **Technical description**: optional implementation notes and constraints, up to 20,000
  characters.
- **Repository link**: optional complete `http://` or `https://` URL.
- **Tags**: zero or more tags from the current project, up to 20 through the API.
- **Acceptance criteria**: optional ordered, verifiable outcomes, one per line.

New stories begin in Todo. Select a card's title to open its editor. The editor can change all five
fields, move the story to any currently valid destination, or permanently delete it. Deletion asks
for confirmation, removes the card, and retains historical activity with the deleted story reference
cleared.

Every story displays a global reference number such as **#42**. Include that number in agent chats,
pull requests, and handoffs to identify a story without copying its UUID.

## Moving stories

Drag a card onto a highlighted valid lane. Invalid destinations do not accept the drop. The story
editor also provides movement buttons, which are the keyboard-accessible alternative to dragging.

Allowed destinations are:

| Current lane | Allowed destinations |
| --- | --- |
| Todo | In Progress, Blocked, Done, Cancelled |
| In Progress | Todo, Blocked, Done, Cancelled |
| Blocked | Todo, In Progress, Done, Cancelled |
| Done | In Progress |
| Cancelled | Todo |

Moving a story to its current lane makes no change. Every successful state change is recorded in
project activity.

## Story priority

Within each lane, stories are ordered by priority. Use the **up** and **down** arrow buttons on a
card to swap it with the adjacent story. The first and last cards cannot move farther in their lane.
Moving a story to another workflow lane places it at the end of that lane.

## Tags and filtering

The Tags area in the board toolbar filters cards immediately in the browser. Selecting several tags
shows a story when it has **any** selected tag. Select an active tag again to remove it, or use
**Clear filters** once filters are active. Tag filters last for the current page session and are not
stored in the database.

Open **Customize** to create a project tag with a name and color. Tag names are unique within a
project without regard to capitalization. Custom tags are available to every story in that project.
Tags cannot currently be renamed or deleted.

## Search, sorting, and history

Use the search field at the top of the board to find stories by title, description, or technical
notes. The sort controls apply on the server, so they work consistently with the JSON API. Open the
**Activity** tab to review the latest 50 project events, including project edits and archive changes.

## Board views

The toolbar contains four visibility presets:

| Preset | Visible lanes |
| --- | --- |
| All lanes | Todo, In Progress, Blocked, Done, Cancelled |
| Work queue | Todo, In Progress, Blocked |
| Focus | In Progress, Blocked |
| Delivery | In Progress, Done |

Open **Customize** to show or hide individual lanes. At least one lane must remain visible, and the
remaining columns expand to use the board width. Lane visibility is saved in browser `localStorage`
under the current project ID. It therefore persists across reloads in that browser but does not
follow a user to another browser or device. Hiding a lane does not change or delete its stories.

## Current limitations

There are no user accounts or access controls. Assignments, comments, pagination, permanent project
deletion, tag editing, and tag deletion are not yet available. The board should be
treated as a trusted local or development application until authentication and authorization are
implemented.
