# Action Items Quick Reference

## Standard Format

### Basic (Acceptable)
```markdown
- [ ] Task description
```

### With Priority (Better)
```markdown
- [ ] **URGENT:** Task description
- [ ] **HIGH:** Task description
- [ ] Task description (default = MEDIUM)
- [ ] **LOW:** Task description
```

### With Date (Best)
```markdown
- [ ] **URGENT:** Task description *(added 2025-11-13)*
```

---

## Priority Levels

| Priority | Keywords | Timeframe |
|----------|----------|-----------|
| **URGENT** | URGENT, ASAP, CRITICAL, BLOCKER | Within 24 hours |
| **HIGH** | HIGH, IMPORTANT, PRIORITY | Within week |
| **MEDIUM** | *(no keyword)* | Default priority |
| **LOW** | LOW, OPTIONAL, NICE-TO-HAVE | When time permits |

---

## Where to Place Action Items

### People Files
```markdown
## Action Items
- [ ] Follow up on meeting
- [ ] Send intro to contact

## Last Updated
2025-11-13
```

### Project Files
```markdown
## Status
- **Current Status:** In Progress
- **Last Updated:** 2025-11-13

## Action Items
- [ ] **URGENT:** Complete deliverable *(added 2025-11-13)*
- [ ] Review feedback *(added 2025-11-12)*
```

### Lead Files
```markdown
## Status
- **Stage:** Proposal Sent
- **Last Updated:** 2025-11-13

## Action Items
- [ ] Follow up if no response *(added 2025-11-13)*
- [ ] Prepare pricing alternatives *(added 2025-11-12)*
```

---

## Best Practices

### DO
- **Be specific:** "Call John about Q1 pricing" not "Follow up"
- **Add dates:** Include `*(added YYYY-MM-DD)*` when creating
- **Use priority markers:** For urgent/time-sensitive items
- **One action per line:** Don't combine multiple actions
- **Use consistent sections:** Always under `## Action Items` heading

### DON'T
- **Vague:** "Do the thing" (too vague)
- **Multiple actions:** "Call John and email Sarah and book meeting" (split these)
- **No context:** Items without enough detail to execute
- **Scattered:** Action items placed randomly in file

---

## Extract All Action Items

### View All Action Items
```bash
python3 scripts/action_items_report.py
```

### Filter by Priority
```bash
python3 scripts/action_items_report.py --priority URGENT
python3 scripts/action_items_report.py --priority HIGH
```

### Export Reports
```bash
python3 scripts/action_items_report.py --format markdown --output action_items.md
python3 scripts/action_items_report.py --format json --output action_items.json
python3 scripts/action_items_report.py --dir people
```

---

## Complete Examples

### People File
```markdown
# Jane Doe

## Contact Information
- **Email:** jane@example.com

## Action Items
- [ ] **HIGH:** Follow up on quoting workflow discussion *(added 2025-11-13)*
- [ ] Send feature clarification *(added 2025-11-13)*
- [ ] Introduce to partner contact *(added 2025-11-10)*

## Last Updated
2025-11-13
```

### Project File
```markdown
# Client AI Project

## Status
- **Current Status:** In Progress
- **Last Updated:** 2025-11-13

## Action Items
- [ ] **URGENT:** Respond to client's latest proposal emails *(added 2025-11-13)*
- [ ] Finalize order of operations document *(added 2025-11-10)*
- [ ] Secure cloud permissions and credentials *(added 2025-11-10)*
```

### Lead File
```markdown
# Acme Corp Partnership

## Status
- **Stage:** Qualification
- **Next Step:** Coffee meeting with decision maker
- **Last Updated:** 2025-11-13

## Action Items
- [ ] **URGENT:** Respond to partnership email *(added 2025-11-13)*
- [ ] Prepare for December dinner (confirm date/time) *(added 2025-11-10)*
- [ ] Follow up on specific opportunities *(added 2025-11-08)*
```

---

## Updating Action Items

### When Completing
```markdown
# Before
- [ ] Task description *(added 2025-11-13)*

# After
- [x] Task description *(added 2025-11-13)*
```

### When Moving to Another File
```markdown
# New file
- [ ] Task description *(moved from 2025-11-13)*
```

---

## Pro Tips

1. **Daily Review:** Run `python3 scripts/action_items_report.py --priority URGENT` each morning
2. **Weekly Planning:** Generate full report for weekly review sessions
3. **Date Everything:** Always add `*(added YYYY-MM-DD)*` for better tracking
4. **Priority Wisely:** Not everything is urgent - save URGENT for true emergencies
5. **Be Specific:** More context = easier execution later

---

## Related Documentation

- **Full Standard:** `.cursor/rules/action-items-standard.mdc`
- **File Standards:** `.cursor/rules/use-for-all-files-made.mdc`
- **Extraction Script:** `scripts/action_items_report.py`
- **CRM Overview:** `README.md`
