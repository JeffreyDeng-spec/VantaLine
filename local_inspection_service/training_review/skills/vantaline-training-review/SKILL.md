---
name: vantaline-training-review
description: Inspect frozen real photos and select whole images for detection training.
---

**Status: Authoritative**

Read `/input/task.json` using `vantaline show`. All inputs are read-only.
Use the image viewing tool on every actual image and all task category references.
Use `vantaline crop --source /input/...png --file /work/crop.png --box '[x1,y1,x2,y2]' --scale 2` to inspect details. Coordinates are original pixels; each crop stores its transform beside the output.

You may accept or reject entire images only. Never add, delete, move or relabel boxes. A missing, incorrect, loose, clipped, ambiguous or duplicate box requires exclude or uncertain with a concrete reason. Empty boxes are not evidence of a negative: inspect the entire original against every task category before accept_negative. Same-class multiple objects all need correct boxes. Boxes cover visible targets only; exclude transparent packaging; each bag of grinding discs is one object; chargers include visible cords/connectors.

An annotation whose status is not completed must be exclude or uncertain, even if the image appears empty. An invalid VLM response cannot become a training negative through this review.

Submit exactly the task's JSON schema once: write `/work/report.json`, then `vantaline submit --file /work/report.json`. Every reason and gap must be a nonempty string of at most 1000 characters. Keep initialization reasons concise. A final chat message does not submit a report; verify that the submit command returns `accepted: true` before completing. A refused report does not authorize a second submission in this invocation. No tools for training, production configuration, image modification, or annotation edits exist.

Initialization sets review_trigger and approved_real_target independently, each integer 20–50, with a reason based on the task and history. Review returns a decision for every listed sample and its exact review_key: accept_positive, accept_negative, exclude or uncertain, each with a reason.

Assessment returns train, collect or pause, approved_real_target (20–50), next_increment (1–50), reason and gaps. Train requires at least the target and 20 approved distinct real images, a positive image, and three independent source groups yielding train/val/test. Missing classes alone do not justify indefinitely postponing training; explain their unavailable metrics. Choose collect only when more photos can resolve the specific gap. Choose pause when capture/annotation conditions need fixing. Never pretend a successful process exit proves visual accuracy.
