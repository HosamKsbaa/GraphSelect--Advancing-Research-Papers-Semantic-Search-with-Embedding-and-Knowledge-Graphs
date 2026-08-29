import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ToolDirectoryComponent } from './tool-directory.component';
import { AgentToolDefinition } from '../../../../core/agent.service';

describe('ToolDirectoryComponent', () => {
  let component: ToolDirectoryComponent;
  let fixture: ComponentFixture<ToolDirectoryComponent>;

  const mockTools: AgentToolDefinition[] = [
    {
      name: 'run_graphselect_traversal',
      description: 'Executes bounded 1-hop BFS citation crawl from seed paper.',
      parameters: {
        type: 'object',
        properties: {
          seed_doi: { type: 'string', description: 'Target seed paper DOI' },
          max_depth: { type: 'integer', description: 'Search depth', default: 1 },
        },
        required: ['seed_doi'],
      },
    },
  ];

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ToolDirectoryComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(ToolDirectoryComponent);
    component = fixture.componentInstance;
    component.tools = mockTools;
    component.agentName = 'ALRSAgent';
    fixture.detectChanges();
  });

  it('should create the component', () => {
    expect(component).toBeTruthy();
  });

  it('should toggle tool expansion state', () => {
    expect(component.isToolExpanded('run_graphselect_traversal')).toBe(false);
    component.toggleTool('run_graphselect_traversal');
    expect(component.isToolExpanded('run_graphselect_traversal')).toBe(true);
    component.toggleTool('run_graphselect_traversal');
    expect(component.isToolExpanded('run_graphselect_traversal')).toBe(false);
  });

  it('should expand and collapse all tools', () => {
    component.expandAll();
    expect(component.isToolExpanded('run_graphselect_traversal')).toBe(true);
    component.collapseAll();
    expect(component.isToolExpanded('run_graphselect_traversal')).toBe(false);
  });

  it('should extract parameters list correctly', () => {
    const props = component.getPropertiesList(mockTools[0]);
    expect(props.length).toBe(2);
    expect(props[0].name).toBe('seed_doi');
    expect(props[0].isRequired).toBe(true);
    expect(props[1].name).toBe('max_depth');
    expect(props[1].isRequired).toBe(false);
  });
});
