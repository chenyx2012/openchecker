import datetime
import threading


class AgentRegistry:
    def __init__(self):
        self.agents = {}
        self.lock = threading.Lock()

    def register_agent(self, agent_id, agent_info):
        with self.lock:
            self.agents[agent_id] = {
                'info': agent_info,
                'status': 'active',
                'last_update': datetime.datetime.now()
            }
            print(f"Agent {agent_id} registered.")

    def update_status(self, agent_id, status):
        with self.lock:
            if agent_id in self.agents:
                self.agents[agent_id]['status'] = status
                self.agents[agent_id]['last_update'] = datetime.datetime.now()
                print(f"Agent {agent_id} status updated to {status}.")
            else:
                print(f"Agent {agent_id} not found.")

    def get_agents(self):
        with self.lock:
            return self.agents.copy()

    def get_agent_info(self, agent_id):
        with self.lock:
            if agent_id in self.agents:
                return self.agents[agent_id]['info']
            else:
                print(f"Agent {agent_id} not found.")
                return None

    def get_agent_status(self, agent_id):
        with self.lock:
            if agent_id in self.agents:
                return self.agents[agent_id]['status']
            else:
                print(f"Agent {agent_id} not found.")
                return None

    def remove_agent(self, agent_id):
        with self.lock:
            if agent_id in self.agents:
                del self.agents[agent_id]
                print(f"Agent {agent_id} removed.")
            else:
                print(f"Agent {agent_id} not found.")
                
if __name__ == "__main__":
    registry = AgentRegistry()

    registry.register_agent("agent1", "Agent 1 description")
    registry.register_agent("agent2", "Agent 2 description")

    agent1_info = registry.get_agent_info("agent1")
    print(f"Agent 1 Info: {agent1_info}")

    agent2_status = registry.get_agent_status("agent2")
    print(f"Agent 2 Status: {agent2_status}")

    registry.remove_agent("agent1")

    agents = registry.get_agents()
    for agent_id, agent_data in agents.items():
        print(f"Agent ID: {agent_id}, Info: {agent_data['info']}, Status: {agent_data['status']}, Last Update: {agent_data['last_update']}")