# Porter declarations (restricted mode test)

Stand-in for Porter's release pipeline. Each JSON file here is a declaration of what Porter may run on a
restricted cluster. The `Publish Porter declarations` workflow pushes each one to the declarations registry
under a tag named after the file and attests it with this workflow's GitHub identity. The cluster's
admission policies verify that identity and compare what Porter applies against the declaration.

- `components/component__<namespace>__<service account>.json`: the containers a system service account may run.
- `nodeclass/nodeclass.json`: the boot documents, image owners and roles a node class may use.
- `app/app-injected.json`: the containers Porter adds to customer app pods.
