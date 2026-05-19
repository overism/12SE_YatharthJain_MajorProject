// AG Grid Tasks Tables

(function initSubjectTaskGrids() {
    if (typeof agGrid === 'undefined') {
        return;
    }

    document.addEventListener("DOMContentLoaded", () => {
        // Show loading screen initially
        const loadingScreen = document.getElementById('tasks-loading');
        if (loadingScreen) {
        loadingScreen.classList.remove('is-hidden');
    }

    const sections = Array.from(document.querySelectorAll(".tasks-table-section"));
    if (sections.length === 0) {
      return;
    }

    const taskTypes = ["Homework", "Exam", "Project", "Study", "Assignment", "Other"];
    const taskTables = {};
    let taskStatusTimeout = null;

    function showTaskStatus(message, type = "info") {
      const el = document.getElementById("taskStatus");
      if (!el) {
        return;
      }

      if (taskStatusTimeout) {
        clearTimeout(taskStatusTimeout);
      }

      el.textContent = message;
      el.className = `status ${type}`;
      el.style.display = "block";

      const timeoutDuration = type === "error" ? 6000 : type === "success" ? 3000 : 4000;
      taskStatusTimeout = setTimeout(() => hideTaskStatus(), timeoutDuration);
    }

    function hideTaskStatus() {
      const el = document.getElementById("taskStatus");
      if (!el) {
        return;
      }

      el.classList.add("hiding");
      setTimeout(() => {
        el.style.display = "none";
        el.classList.remove("hiding");
      }, 300);

      if (taskStatusTimeout) {
        clearTimeout(taskStatusTimeout);
        taskStatusTimeout = null;
      }
    }

    function isIsoDate(value) {
      const dateValue = String(value || "");
      if (!/^\d{4}-\d{2}-\d{2}$/.test(dateValue)) {
        return false;
      }

      const [year, month, day] = dateValue.split("-").map(Number);
      const date = new Date(year, month - 1, day);

      return (
        !Number.isNaN(date.getTime()) &&
        date.getFullYear() === year &&
        date.getMonth() === month - 1 &&
        date.getDate() === day
      );
    }

    function formatDateForGrid(value) {
      if (!isIsoDate(value)) {
        return value || "";
      }

      const [year, month, day] = value.split("-");
      return `${day}/${month}/${year}`;
    }

    function normaliseDateValue(value) {
      const raw = String(value || "").trim();
      if (isIsoDate(raw)) {
        return raw;
      }

      const slashMatch = raw.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
      if (!slashMatch) {
        return "";
      }

      const day = slashMatch[1].padStart(2, "0");
      const month = slashMatch[2].padStart(2, "0");
      const year = slashMatch[3];
      const iso = `${year}-${month}-${day}`;
      return isIsoDate(iso) ? iso : "";
    }

    function isPastDate(isoDate) {
      const selectedDate = new Date(`${isoDate}T00:00:00`);
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      return selectedDate < today;
    }

    function formatLocalIsoDate(date) {
      const year = date.getFullYear();
      const month = String(date.getMonth() + 1).padStart(2, "0");
      const day = String(date.getDate()).padStart(2, "0");
      return `${year}-${month}-${day}`;
    }

    function calculateDaysRemaining(isoDate) {
      const selectedDate = new Date(`${isoDate}T00:00:00`);
      const today = new Date();
      today.setHours(0, 0, 0, 0);

      const millisecondsPerDay = 24 * 60 * 60 * 1000;
      return Math.max(0, Math.round((selectedDate - today) / millisecondsPerDay));
    }

    function getTaskProgressColor(params) {
      const percent = Number(params.value?.toString().match(/\d+/)?.[0]);

      if (isNaN(percent)) {
        return { backgroundColor: "#777", color: "#fff" };
      }

      let r, g, b;

      if (percent <= 50) {
        const ratio = percent / 50;
        r = 255;
        g = Math.round(49 + (211 - 49) * ratio);
        b = Math.round(49 + (89 - 49) * ratio);
      } else {
        const ratio = (percent - 50) / 50;
        r = Math.round(255 - (255 - 0) * ratio);
        g = Math.round(211 + (191 - 211) * ratio);
        b = Math.round(89 - (89 - 99) * ratio);
      }

      return {
        backgroundColor: `rgb(${r}, ${g}, ${b})`,
        color: percent > 60 ? "white" : "black",
        fontWeight: "700"
      };
    }

    async function setProgressValue(params) {
      const progress = Number(String(params.newValue).replace("%", ""));
      if (!Number.isInteger(progress) || progress < 0 || progress > 100) {
        showTaskStatus("Status must be a whole number from 0 to 100", "error");
        return false;
      }

      params.data.status = `${progress}%`;
      
      // Update in database
      const success = await updateTask(params.data.taskID, 'status', `${progress}%`);
      if (!success) {
        return false; // Revert the change
      }
      
      return true;
    }

    function setDaysValue(params) {
      const daysRemaining = Number(params.newValue);
      if (!Number.isInteger(daysRemaining) || daysRemaining < 0 || daysRemaining > 365) {
        showTaskStatus("Time remaining must be a whole number from 0 to 365 days", "error");
        return false;
      }

      params.data.time = daysRemaining;
      return true;
    }

    async function setTypeValue(params) {
      if (!taskTypes.includes(params.newValue)) {
        showTaskStatus("Type must be selected from the dropdown options", "error");
        return false;
      }

      params.data.type = params.newValue;
      
      // Update in database
      const success = await updateTask(params.data.taskID, 'type', params.newValue);
      if (!success) {
        return false; // Revert the change
      }
      
      return true;
    }

    async function setDateValue(params) {
      const isoDate = normaliseDateValue(params.newValue);
      if (!isoDate) {
        showTaskStatus("Due date must be a valid date", "error");
        return false;
      }

      if (isPastDate(isoDate)) {
        showTaskStatus("Due date cannot be in the past", "error");
        return false;
      }

      params.data.date = isoDate;
      params.data.time = calculateDaysRemaining(isoDate);
      
      // Update in database
      const success = await updateTask(params.data.taskID, 'date', isoDate);
      if (!success) {
        return false; // Revert the change
      }
      
      params.api.refreshCells({ rowNodes: [params.node], columns: ["time"], force: true });
      return true;
    }

    function createGridOptions(rowData) {
      return {
        defaultColDef: {
          flex: 1,
          minWidth: 135,
          editable: true,
          cellClass: "editable-cell",
          resizable: true
        },
        columnTypes: {
          trafficLight: {
            cellClassRules: {
              'cell-red': params => Number(params.value) <= 3,
              'cell-yellow': params => {
                const value = Number(params.value);
                return value > 3 && value <= 7;
              },
              'cell-green': params => Number(params.value) > 7
            },
            valueFormatter: params => `${params.value} Days`
          },
          progressGradient: {
            cellStyle: getTaskProgressColor
          }
        },
        columnDefs: [
          {
            headerName: "Task",
            field: "task",
            cellClass: ["editable-cell", "editable-text-cell"],
            valueSetter: async params => {
              const value = String(params.newValue || "").trim();
              if (!value) {
                showTaskStatus("Task name cannot be empty", "error");
                return false;
              }

              params.data.task = value;
              
              // Update in database
              const success = await updateTask(params.data.taskID, 'task', value);
              if (!success) {
                return false; // Revert the change
              }
              
              return true;
            }
          },
          {
            headerName: "Due Date",
            field: "date",
            cellEditor: "agDateStringCellEditor",
            cellDataType: "dateString",
            valueFormatter: params => formatDateForGrid(params.value),
            valueSetter: setDateValue,
            cellClass: ["editable-cell", "editable-date-cell"]
          },
          {
            headerName: "Type",
            field: "type",
            cellEditor: "agSelectCellEditor",
            cellEditorParams: { values: taskTypes },
            valueSetter: setTypeValue,
            cellClass: ["editable-cell", "editable-select-cell"]
          },
          {
            headerName: "Status",
            field: "status",
            type: "progressGradient",
            valueSetter: setProgressValue,
            cellClass: ["editable-cell", "editable-number-cell"]
          },
          {
            headerName: "Time Remaining",
            field: "time",
            editable: false,
            type: "trafficLight",
            comparator: (a, b) => Number(a) - Number(b),
            cellClass: "calculated-cell"
          }
        ],
        rowData,
        stopEditingWhenCellsLoseFocus: true,
        animateRows: true,
        theme: agGrid.themeQuartz.withParams({
          accentColor: "#F5761C",
          backgroundColor: "#FFFFFF",
          borderColor: "#000000",
          borderRadius: 2,
          borderWidth: 1,
          browserColorScheme: "inherit",
          cellHorizontalPaddingScale: 0.7,
          chromeBackgroundColor: "#FFFFFF",
          columnBorder: true,
          fontFamily: 'Arial, sans-serif',
          fontSize: 14,
          foregroundColor: "#555B62",
          headerBackgroundColor: "#FFFFFF",
          headerFontSize: 16,
          headerFontWeight: 600,
          headerTextColor: "#000000",
          oddRowBackgroundColor: "#FAFAFA",
          rowBorder: true,
          rowVerticalPaddingScale: 0.9,
          sidePanelBorder: true,
          spacing: 8,
          wrapperBorder: true,
          wrapperBorderRadius: 15
        })
      };
    }

    async function loadTasks() {
      try {
        const response = await fetch('/get_tasks');
        if (!response.ok) {
          throw new Error('Failed to fetch tasks');
        }
        const data = await response.json();
        return data.tasks || [];
      } catch (error) {
        console.error('Error loading tasks:', error);
        showTaskStatus('Failed to load tasks from database', 'error');
        return [];
      }
    }

    async function updateTask(taskID, field, value) {
      try {
        const response = await fetch('/update_task', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ taskID, field, value })
        });
        
        if (!response.ok) {
          const error = await response.json().catch(() => ({}));
          throw new Error(error.error || 'Failed to update task');
        }
        
        return true;
      } catch (error) {
        console.error('Error updating task:', error);
        showTaskStatus(`Failed to update task: ${error.message}`, 'error');
        return false;
      }
    }

    async function populateGrids() {
      const tasks = await loadTasks();
      
      // Group tasks by subjectID
      const tasksBySubject = {};
      tasks.forEach(task => {
        const subjectKey = `subject-${task.subjectID}`;
        if (!tasksBySubject[subjectKey]) {
          tasksBySubject[subjectKey] = [];
        }
        tasksBySubject[subjectKey].push(task);
      });

      // Populate each grid with its tasks
      Object.keys(taskTables).forEach(tableId => {
        const grid = taskTables[tableId];
        const subjectTasks = tasksBySubject[tableId] || [];
        grid.setGridOption('rowData', subjectTasks);
      });

      // Hide loading screen after tasks are loaded
      setTimeout(() => {
        const loadingScreen = document.getElementById('tasks-loading');
        if (loadingScreen) {
          loadingScreen.classList.add('is-hidden');
        }
      }, 500);
    }

    sections.forEach((section, index) => {
      const gridDiv = section.querySelector(".task-grid");
      const tableId = gridDiv?.dataset.taskTableId || section.dataset.taskTableId;
      if (!gridDiv || !tableId) {
        return;
      }

      // Initialize grids with empty data, will be populated after loading
      taskTables[tableId] = agGrid.createGrid(gridDiv, createGridOptions([]));
    });

    // Load and populate tasks after grids are initialized
    populateGrids();

    function setDefaultDueDate(form) {
      const dueDate = form.querySelector(".taskDueDate");
      if (!dueDate) {
        return;
      }

      const tomorrow = new Date();
      tomorrow.setDate(tomorrow.getDate() + 1);
      const today = formatLocalIsoDate(new Date());
      dueDate.min = today;
      dueDate.value = formatLocalIsoDate(tomorrow);
    }

    function clearFieldErrors(form) {
      form?.querySelectorAll(".field-error").forEach(field => {
        field.classList.remove("field-error");
      });
    }

    function openTaskForm(section) {
      const formContainer = section.querySelector(".task-form");
      const form = section.querySelector(".taskFormData");
      if (!formContainer || !form) {
        return;
      }

      form.reset();
      clearFieldErrors(form);
      setDefaultDueDate(form);
      formContainer.style.display = "block";
      formContainer.setAttribute("aria-hidden", "false");
      section.querySelector(".taskTitle")?.focus();
    }

    function closeTaskForm(section) {
      const formContainer = section.querySelector(".task-form");
      const form = section.querySelector(".taskFormData");
      if (!formContainer || !form) {
        return;
      }

      formContainer.style.display = "none";
      formContainer.setAttribute("aria-hidden", "true");
      clearFieldErrors(form);
    }

    function flagField(field) {
      field.classList.remove("field-error");
      void field.offsetWidth;
      field.classList.add("field-error");
    }

    function validateTaskForm(form) {
      clearFieldErrors(form);

      const title = form.querySelector(".taskTitle");
      const dueDate = form.querySelector(".taskDueDate");
      const type = form.querySelector(".taskType");
      const status = form.querySelector(".taskStatusInput");
      const subject = form.querySelector(".subjectID");
      const fields = [title, dueDate, type, status, subject];
      const invalidFields = fields.filter(field => !field || !field.value.trim());

      invalidFields.forEach(flagField);
      if (invalidFields.length > 0) {
        showTaskStatus("Please fill in all required fields", "error");
        invalidFields[0]?.focus();
        return null;
      }

      const isoDate = normaliseDateValue(dueDate.value);
      const progress = Number(status.value);

      if (!isoDate || isPastDate(isoDate)) {
        flagField(dueDate);
        showTaskStatus(!isoDate ? "Please enter a valid due date" : "Due date cannot be in the past", "error");
        dueDate.focus();
        return null;
      }

      if (!taskTypes.includes(type.value)) {
        flagField(type);
        showTaskStatus("Please select a valid task type", "error");
        type.focus();
        return null;
      }

      if (!Number.isInteger(progress) || progress < 0 || progress > 100) {
        flagField(status);
        showTaskStatus("Status must be a whole number from 0 to 100", "error");
        status.focus();
        return null;
      }

      return {
        task: title.value.trim(),
        date: isoDate,
        type: type.value,
        status: `${progress}%`,
        time: calculateDaysRemaining(isoDate),
        savePayload: {
          subjectID: subject.value,
          taskTitle: title.value.trim(),
          taskDueDate: isoDate,
          taskType: type.value,
          taskStatusInput: progress
        }
      };
    }

    sections.forEach(section => {
      const openButton = section.querySelector(".new-task-btn");
      const formContainer = section.querySelector(".task-form");
      const form = section.querySelector(".taskFormData");
      const closeBtn = section.querySelector(".closeTaskBtn");
      const cancelBtn = section.querySelector(".cancelTaskBtn");

      openButton?.addEventListener("click", () => openTaskForm(section));
      closeBtn?.addEventListener("click", () => closeTaskForm(section));
      cancelBtn?.addEventListener("click", () => closeTaskForm(section));

      form?.addEventListener("submit", async event => {
        event.preventDefault();
        const task = validateTaskForm(form);
        if (!task) {
          return;
        }

        const tableId = section.dataset.taskTableId;
        const targetGrid = taskTables[tableId];
        if (!targetGrid) {
          showTaskStatus("Could not find the selected task table", "error");
          return;
        }

        try {
          const response = await fetch(form.action, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(task.savePayload)
          });

          const result = await response.json().catch(() => ({}));
          if (!response.ok) {
            showTaskStatus(result.error || "Could not save task", "error");
            return;
          }

          delete task.savePayload;
          task.taskID = result.taskID;
          task.time = result.daysRemaining;

          // Reload all tasks to ensure grids are in sync
          await populateGrids();
          closeTaskForm(section);
          showTaskStatus("Task saved successfully", "success");
        } catch (error) {
          showTaskStatus("Could not save task. Please try again.", "error");
        }
      });
    });
  })
})();