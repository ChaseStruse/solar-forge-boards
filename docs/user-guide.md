# User guide

The browser workspace lives at `/ui/projects`. Solar Forge Boards currently uses a dark cyberpunk
theme and is designed around projects containing story cards.

## Projects

Create a project from the Projects page with a unique name and an optional description. Opening a
project shows its five workflow lanes and creates no stories automatically. New projects receive the
four default tags: Business, Coding, Configuration, and Spike.

Projects cannot currently be renamed or deleted through the UI or API.

## Stories

Select **Forge a story** on a project board. A story supports:

- **Title**: required, up to 200 characters.
- **Description**: optional user, business, or outcome context, up to 10,000 characters.
- **Technical description**: optional implementation notes and constraints, up to 20,000
  characters.
- **Repository link**: optional complete `http://` or `https://` URL.
- **Tags**: zero or more tags from the current project, up to 20 through the API.

New stories begin in Todo. Select a card's title to open its editor. The editor can change all five
fields, move the story to any currently valid destination, or permanently delete it. Deletion asks
for confirmation, removes the card, and retains historical activity with the deleted story reference
cleared.

## Moving stories

Drag a card onto a highlighted valid lane. Invalid destinations do not accept the drop. The story
editor also provides movement buttons, which are the keyboard-accessible alternative to dragging.

Allowed destinations are:

| Current lane | Allowed destinations |
| --- | --- |
| Todo | In Progress, Blocked, Cancelled |
| In Progress | Todo, Blocked, Done, Cancelled |
| Blocked | Todo, In Progress, Cancelled |
| Done | In Progress |
| Cancelled | Todo |

Moving a story to its current lane makes no change. Every successful state change is recorded in
project activity.

## Tags and filtering

The Tags area in the board toolbar filters cards immediately in the browser. Selecting several tags
shows a story when it has **any** selected tag. Select an active tag again to remove it, or use
**Clear filters** once filters are active. Tag filters last for the current page session and are not
stored in the database.

Open **Customize** to create a project tag with a name and color. Tag names are unique within a
project without regard to capitalization. Custom tags are available to every story in that project.
Tags cannot currently be renamed or deleted.

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

There are no user accounts or access controls. Assignments, comments, search, pagination, project
editing, project deletion, tag editing, and tag deletion are not yet available. The board should be
treated as a trusted local or development application until authentication and authorization are
implemented.
