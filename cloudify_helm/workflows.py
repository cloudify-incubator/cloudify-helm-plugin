########
# Copyright (c) 2019 Cloudify Platform Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
#    * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    * See the License for the specific language governing permissions and
#    * limitations under the License.

from cloudify.exceptions import NonRecoverableError


def _helm_operation(ctx,
                    operation,
                    node_ids,
                    node_instance_ids,
                    node_type,
                    **kwargs):
    graph = ctx.graph_mode()
    sequence = graph.sequence()
    # Iterate over all node instances of type "node_type"
    for node_instance in ctx.node_instances:
        if node_ids and (node_instance.node.id not in node_ids):
            continue
        if node_instance_ids and (node_instance.id not in node_instance_ids):
            continue
        if node_type in node_instance.node.type_hierarchy:
            ctx.logger.info("Adding node instance: {id}".format(
                            id=node_instance.id))
            sequence.add(
                node_instance.execute_operation(
                    operation,
                    kwargs=kwargs,
                    allow_kwargs_override=True)
            )

    return graph


def update_repositories(ctx, node_ids, node_instance_ids, flags):
    # TODO: Remove the check when 4.X is not supported, add to flags
    #  parameter type: list in plugin.yaml
    if type(flags) is not list:
        raise NonRecoverableError('Flags parameter must be a list.')
    _helm_operation(ctx,
                    "helm.update_repo",
                    node_ids,
                    node_instance_ids,
                    'cloudify.nodes.helm.Repo',
                    flags=flags).execute()
