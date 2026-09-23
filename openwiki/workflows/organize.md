---
type: Workflow
title: Organize parsed documents
description: How Classify, Split, and Section use grounded Parse results to create cited page labels, grouped outputs, and section maps.
tags: [workflow, organize, classify, split, sections]
verified:
  - by: openwiki/0.5.2
    at: 2026-09-23T15:07:44.901Z
sources:
  - id: openwiki-source-06643b6801b74f288c9371f8
    resource: repo://app_pages/organize.py
  - id: openwiki-source-d0ca7b2f3bc35dc0f2a1020d
    resource: repo://paperplane/ade_workflows.py
  - id: openwiki-source-e6e4dfe11c3b4c12b3595db1
    resource: repo://paperplane/contracts.py
generated: { by: "codex", at: "2026-09-23T15:07:44.901Z" }
---

# Organize parsed documents

Organize works on successful Parse results kept in the current Streamlit session. Choose a parsed document, then use Classify, Split, or Section. The page offers these deterministic workflows over the parsed structure; the current implementation does not call a model to make the organization decisions.

## Classify pages

Enter the allowed class names, one per line. The UI uses each name as both the class name and its description. For each page, classification gathers the ranges of its grounded blocks and checks the corresponding Markdown text against classes in the order supplied. It returns the first class with a matching term longer than three characters. If none matches, it assigns the first allowed class and adds a warning that the classification is a deterministic partial. An empty class list is rejected.

The result includes a page number, selected label, reason, and source ranges. The matching reason identifies the source term; the fallback reason says no deterministic keyword match was found.

## Split by class

Split applies the same classification rules, groups pages by their selected class, and returns each group's page numbers, Markdown, and ranges. Page Markdown slices are joined with a visible `<!-- PAGE BREAK -->` marker. Any partial-classification warnings are carried into the split response.

## Detect sections

Section checks each page for grounded blocks and uses the first block with ranges as that page's section start. If it is not marked with the semantic role `title` or `heading`, the result includes a warning that the first grounded block is being used as a partial. The section title is the first line of that block's text, capped at 160 characters. The output includes section numbering, page number, start block reference, ranges, and the original document Markdown; the UI can download the JSON as `sections.json`.

Ranges use half-open Unicode code-point offsets into the document Markdown. They identify source text and are not page-local offsets.

## Related pages

- [Paperplane system overview](../architecture/system-overview.md)
- [Contracts and exported formats](../concepts/contracts-and-exports.md)
- [Parse workflow and grounded assembly](parse-document.md)
